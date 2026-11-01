"""The player-model swap: ``randomize-full --player-character SPECIES``
(D111, D112; Step 2.21a).

Not a registered :class:`Feature`: packs take numbers, and this takes a
species name.  randomize-full applies it after the packs, as one build
layer, ``player model <species>`` (D28).

**Mechanism B (D112).**  The player stays species ``garret4``: its
PlayerControl (``ai`` = player), its ``player`` flag 0x20 (so level
triggers and key locks work), its speeds, damage table and sounds.  Only
the body it wears changes.  The build writes ``config.xbr`` and
``fx.xbr`` (W1-W7 and W14-W16, as its gameplay mode says), for a body the
bake serves ``characters.xbr`` and ``index.xbr`` too (B; W17 for a clip
that switches on its own field), and up to eleven C shims
into ``default.xbe``, each only for a body that needs it (X4, X3, X7,
X11, X12, X8, X9, X10, X16) or an option that asks for it (X13, X14),
and X17's one cvar default, X18 when a light column's multiplier
reaches 1.0, X19 when the camera point sits above garret4's eye and
X25's camera rig when the body is drawn at another size than his:

- **W1** ``config.xbr`` ``critters_engine/garret4/body`` points at the
  species' own body string (:func:`point_keyed_string`: garret4's string
  is shared, so the cell is retargeted, never rewritten).
- **W2** the species' ``scale``, when it has one, goes into garret4's
  empty ``scale`` cell, and ``boundRadius`` becomes the larger of
  garret4's and the species' ``boundRadius`` × that scale.
- **W3** each ``attacks_anims`` ``Anim`` names a clip the body has
  (:func:`substitutes`): every attack one of its attack clips (those
  that switch its damage marker on, and since Step 2.64 every
  ``attack*`` clip, which X3 gives a hit box), the combo its first three;
  ``Rate`` is left to W5 (D112).
- **W4** ``fx.xbr``: the scale of every fx transform bound to
  ``m_stafftop`` / ``m_staffbottom`` (60, in 30 graphs) becomes 0.001,
  hiding the staff that floats beside any body but garret4's.
- **W6** (Step 2.24f) ``fx.xbr``: the element effects' particles come
  from the body's action point (D219, :func:`action_point`), not 3 m to
  the side.  For a body with a hand those 60 transforms bind to its
  hands instead of garret4's staff bones (the top end its right hand,
  the bottom its left: :func:`hand_bones`; :func:`follow_hands`); for
  one without (Step 2.64) they stay unbound at a fixed point, where its
  ``m_damage`` hits, else in front of its chest (:func:`at_point`).
  Either way the staff's blades under them shrink to 0.001 instead, and
  (Step 2.182, D707) the power heads are reshaped for what the hand
  holds (:mod:`~azurik_mod.patches._player_power_fx`).
- **W15** (Step 2.77b) ``fx.xbr``: the armors' transforms bound to a
  node of garret4's body that the body lacks (``m_chest``, ``m_skull``,
  the limb markers) stay unbound at garret4's authored point; each one's
  translate and scale (and an inherit-mode-1 child's scale) become that
  times the body's height over his, so the helm, breastplate, wings and
  shields sit on the body, sized to it (:func:`fit_armor`).
- **W16** (Step 2.75d, AZ-450) ``config.xbr`` ``critters_damage``: every
  critter wears its body's default fx (0x43700), the player too, so a
  body whose default fx holds a damage platform nothing switches off
  (tesla_tree's, ``tesla``) hurt the player wearing it, garret4 taking
  the type's base damage where the species takes none; garret4's cell
  for each type such a field deals := the species' own
  (:func:`field_damage`; tesla_tree: ``tesla`` 0.0).
- **W17** (Step 2.75e, AZ-453) ``characters.xbr``, ``index.xbr`` and
  W3's names: a field of the body's default fx that a marker switches on
  hurts its wearer too, the game checking no platform hit against its
  owner (balthazar_airship's ``damageBox``, which ``m_lifedrainswitch``
  turns on in his ``attack_2`` and ``onPlayer`` sets on the player
  critter: ``norm_2``, 15 HP, in each column that plays it), so each pick
  that keys such a marker (:func:`self_drains`) plays a copy of its clip
  without that marker's tracks, ``characters/<body>/p/<n>``
  (:data:`SELF_DIR`), which W3 alone names: every other step reads the
  pick, as the copy moves, lasts and hits as it does.  NPCs of the body
  keep the clip.
- **W22** (Step 2.131, AZ-603, D343) ``characters.xbr``, ``index.xbr``
  and X11's table: a marker whose transform in the body's default fx
  reaches a camera or a critter generator, directly or through switches
  and latches (:func:`scripted_switches`: ``m_dying`` on
  bosses/air_guardian, bosses/fire_guardian and balthazar_airship),
  scripts a scene for its wearer too: air_guardian's ``die`` keys it
  for its 9.667 s, which turns on a death camera that freezes the
  player's input and drops ``frag_air_4``, the air disc fragment (the
  owner's 2.76 play: the drop, then a stalled game).  Each asked slot
  but the hits whose clip keys such a marker plays a copy without those
  tracks, ``characters/<body>/q/<clip>`` (:data:`QUIET_DIR`,
  :func:`quiet_fills`): the death slots 23-27 ``q/die`` on those three
  bodies, the death's motion, length and explosions kept, its camera
  and drop gone; since Step 2.175 (AZ-611) each attack pick that keys
  one plays such a copy too, ``q/<n>``, in every mode
  (:func:`attack_copies`: bosses/fire_guardian's ``attack_2``, whose
  ``m_shards`` drives its ``fire_shard`` generator, in 12 of
  guard_fire1's 24 columns), and its victories' ``v/`` copies are
  without them.  NPCs of the body keep the clip.
- **B** (Step 2.87; D226, D238) ``characters.xbr`` and ``index.xbr``,
  under ``missing_anims`` "garret4" (:func:`bakes`; the default in
  both modes, :data:`MODE_ANIMS`; "own" bakes only the victories, W21) for a body
  :data:`azurik_mod.assets.retarget.MAPS` lists (balthazar_airship;
  Step 2.88: keylord, overlord, the three elementals and the townswomen
  and children; Step 2.89, D239: the townsmen) and for a body with no
  clips (as timers, its root bone riding his ``m_feet`` / D alone, Step
  2.127): the garret4 clips X11's table and
  W3 name, baked onto the body's rig
  as ``characters/<body>/g4/<clip>``
  (:func:`~azurik_mod.assets.retarget.bake_body`): each mapped bone moves
  as garret4's, with his length, root motion and markers (``m_feet``,
  ``m_grab`` and ``m_attacklevel`` added to the body), so neither X4 nor
  X9 serves them; the roll's is drawn about the body's centre at its
  drawn scale (:func:`~azurik_mod.assets.retarget.centred`, Step 2.133,
  AZ-608: drawn x D, garret4's ``m_feet`` led it 4.07 m at D 2), and
  since Step 2.175 (AZ-623) each attack pick whose clip moves ``m_feet``
  too, its damage markers kept (the bake's ``lunges``; a body's own
  clip, garret4's own at his size included, as a copy,
  :func:`attack_copies`: garret4's attack_3 led 0.78 m at D 2).  W3
  puts ``g4/roll_forward`` in a string no pick
  plays, and in garret4's exact as many of garret4's own attack clips
  as the table's strings can hold (seven or eight columns: each ``Anim``
  string is exactly its vanilla clip's length, and hose_attack_3's is
  shared; :func:`substitutes`); the other attack columns keep the body's
  own clips, in garret4's time with his box and window (X3) there.
  Every lookup of a pick on the body resolves a baked one to garret4's
  clip (:func:`source_clip`).
- **X4** (Step 2.21b) ``default.xbe``: when the clip the roll plays
  doesn't move the body's ``m_feet`` (:func:`moves_root`; every body
  with clips but garret4's and one B bakes, which rolls on
  ``g4/roll_forward``), the C shim ``player_model/roll.c`` at the root-motion
  sampler's CALL (VA 0x8C6AE) rolls the player by garret4's
  ``roll_forward`` root motion over the model's own roll time
  (:func:`install_roll_shim`).
- **X3** ``default.xbe``, for a body where some attack plays a clip
  that switches no damage marker on (garret4's exact, every body with
  clips: Step 2.24f; own body, also every attack whose own box fails the
  reach test, :func:`reach_misses`, Step 2.69): a shim gives those attacks
  garret4's hit box mid-attack
  (:mod:`azurik_mod.patches._player_damage_marker`, Step 2.21c), ahead
  of the action point (Step 2.64), and keeps the body's own marker for
  the others; in garret4's exact each column takes garret4's own box
  and window for the clip it plays in vanilla, where garret4 holds it
  (Step 2.68, :func:`~azurik_mod.patches._player_damage_marker.garret4_boxes`),
  and so does a body with no clips in every mode, which plays exactly
  those clips (Step 2.75e, AZ-473).
  X4, when the body needs it, is installed first.
- **X7** (Step 2.21d) ``default.xbe``, for every body with clips: the
  C shim ``player_model/hit_reaction.c`` at the hit handler's CALL
  (VA 0x8D682) plays the body's ``ouch_1`` (else its ``idle``, else
  the roll's clip) for any hit reaction (anim 37-42), at the rate that
  ends it in garret4's 0.4 s (AZ-291; :func:`install_hit_shim`), and
  ends the crossfade from the interrupted clip at once, so
  that clip's damage window can't deal damage inside the reaction (Step
  2.22l, AZ-304).
- **X11** (Step 2.66) ``default.xbe``, for a body with clips that lacks
  a base clip the player asks for: the C shim ``player_model/slots.c`` at
  the species load's CALL of species_clip_lookup (VA 0x4B948) gives each
  such slot one of the body's own clips, a very similar one in its own
  time, else (``missing_anims`` "garret4", D226/D229) the closest one
  marked garret4-timed for a slot garret4 has, or ("own") the closest
  one everywhere (each mode's default: :data:`MODE_ANIMS`); so a body
  with no idle starts each level on
  a clip, not its bind pose (AZ-303), and a jump, a swim or a death plays
  one (:mod:`azurik_mod.patches._player_slots`).  Since Step 2.131 the
  player's slots are looked up under the table's name first, so W22's
  copy takes a death slot the body fills by name.
- **X12** (Step 2.67) ``default.xbe``: ``player_model/borrow.c`` plays a
  slot X11 marked garret4-timed in garret4's clip length (the clip
  change's VA 0xCAF6B, and 0xCAEC0 for a clip played again); a body with
  no clips plays garret4's clips baked as timers (B), its attacks too
  (0x7E3F0, ``g4/<name>``), with X3's hit box and window for each
  (:mod:`azurik_mod.patches._player_borrow`).
- **X44** (Step 2.161b2, AZ-688) ``default.xbe``: ``player_model/borrow_first.c``
  at X12's attack site (0x7E3F0) in its place, for a body that borrows
  garret4's attacks and owns one of their vanilla names (keylord,
  balthazar, golem, kingkong, overlord, air_elemental, air_elemental_boss
  and water_elemental under a picked Axion staff or hoe): the player's
  columns look up ``g4/<name>`` before ``<name>``, so every column swings
  garret4's attack with the prop where his box is.
- **X8** (Step 2.23c) ``default.xbe``, for a body with a mesh top and no
  usable ``m_head`` marker (none, or one resting under half its top:
  every one but garret4's and balthazar_airship's), drawn at a scale
  above 0: the C shim ``player_model/eye.c`` at the camera point's marker
  lookup (VA 0x41F67) aims the camera at garret4's share of the body's
  drawn height (his ``m_head`` over his mesh's top, 0.9954, of its mesh
  top; Step 2.107), not at its feet (AZ-304, D128; :func:`camera_plan`,
  :func:`install_eye_shim`); while the player swims it measures the body
  from where the game draws it: over the water it aims at the land point,
  raised only to keep the camera its first swim margin's height over the
  surface (Step 2.116, AZ-311), and once the top is under in a dive (+0x15C
  past 2.55 m, back over at 2.35 m, garret4's own crossing depths: Steps
  2.116, 2.116b) its second margin under it
  (0.5 and 3.5 m, or :func:`swim_margins`' at X25's rig scale), so the
  camera stays on the body's side of the water (Steps 2.80, 2.80b;
  AZ-413, AZ-414), under the water never floored at the feet (Step
  2.107).  Sized to garret4's height, an upright body aims it at
  garret4's eye height (Step 2.68), the same point.
- **X9** (Step 2.63) ``default.xbe``, for a body with clips but not the
  ladder's (every one but garret4's and one B bakes, which gains
  ``m_grab`` and plays his baked climb clips): the C shim
  ``player_model/climb.c``
  at the move-state setter's CALL of the aligned clip change (VA 0x8BDF3)
  and the climb tick's two CALLs of anim_change (0x883CB, 0x88733) plays
  the body's stand-in clip (idle, else idle_1, walk, run, the roll's) for
  each ladder, hoist and step-up move and climb loop it lacks, each
  aligned move in garret4's time, and places the body on the rungs and at
  each move's end where garret4 is: a swapped body latched onto a ladder
  with no clip to end the latch (the owner: Balthazar "had trouble
  latching onto the ladder"; :func:`install_climb_shim`).  The hard
  landing (``touchdown``, 0x8B0D4 and 0x8B18C) and the overhead hang
  (``hang_start``, 0x8A4E3) call 0x42430 directly; X9 takes those CALLs
  too (Step 2.66b): the stand-in in garret4's time, not a lock until the
  clip already playing ends; a stand-in shorter than his clip plays at
  its rate x its length over his, also through the rate each setter
  caller sets after it (its CALL of 0x30940; Step 2.96, AZ-489).  On those
  bodies and every one without garret4's ``m_root`` (Step 2.63b,
  AZ-393), at the PlayerPhysics constructor's CALL of 0x84A40 (VA
  0x84E59), each ladder offset that leaves (0, 0, 0) takes garret4's,
  so the latch sweeps where his does (:func:`install_climb_offsets`).
  Away from x1 its zipline landings hang the drawn body by the top of its
  own hang pose, 0.05 m under the cable as garret4's (Step 2.104, AZ-526;
  Step 2.106, AZ-529: :func:`hang_scale`).
- **X10** (Step 2.64) ``default.xbe``, for a body with more attack clips
  than the combo's three (:func:`rotation`; balthazar_spider's ten): the
  C shim ``player_model/attack_rotation.c`` at player_attack_enter's
  CALL of anim_change (VA 0x889A6) plays the next of those clips each
  swing, in turn (D219 amended: "give them as many attacks as we can";
  :func:`install_rotate_shim`); not in garret4's exact, where each
  column plays its one clip in garret4's time (Step 2.68).  With the
  attack balance on, each swing takes that clip's Rate and the Damage
  multiplier the balance gives it in the swinging column (Step 2.69).  In
  own body the ring keeps only the clips that can hit a target on the
  ground (:func:`hitting_ring`), and a swing in basic1-3 takes its clip's
  W19 chain point at the Rate it plays at, with the balance or without
  it (Step 2.104, AZ-523; :func:`chain_terms`).
- **X13** (Step 2.70; D222, D223) ``default.xbe``, only when an option
  asks for it (``attack_reach`` other than 1.0, ``attack_ground``, the
  balance's reach bump): the C shim ``player_model/attack_box.c`` at the
  damage pass's box build (VA 0x43B47) makes the player's hit boxes reach
  ``attack_reach`` times as far, :data:`REACH_BUMP` times farther still
  in a short melee column (Step 2.69), and fills each attack's box: its
  bounds, back to the feet, across the facing line and down to the floor
  (Step 2.132, AZ-605; :func:`fill_mask`, :func:`install_attack_box_shim`).
- **X14** (Step 2.71) ``default.xbe``, with ``sounds="own"`` (D231)
  for a model whose species has sounds of its own: the C shim
  ``player_model/sounds.c`` at the two CALLs of 0x4B680 that bind the
  player's clip sounds (VAs 0x4B93C, 0x7E3DD) binds the model's own
  sound per role, Garret's where it has none (D232;
  :mod:`azurik_mod.patches._player_sounds`, :func:`install_sounds_shim`).
  With it (Step 2.72) **W9-W11** ``config.xbr``: the
  attack shouts the model's own sounds replace go empty, and garret4's
  ``critters_sounds`` ``ouch``, ``ambient`` and hit rows take the
  species'; **W12** the townspeople's speech lines in X14's table
  (D233); **X15** ``default.xbe``: the jump's and the steps'
  ``fx/sound/player/*`` paths load the species' own, where it has them
  (D233).
- **X16** (Step 2.77) ``default.xbe``, for a body with no ``m_jump``
  marker (every one but garret4's): the C shim ``player_model/wings.c``
  at the critter bind interface's two CALLs (VAs 0x44355 and 0x44389)
  gives the player a virtual ``m_jump`` that pulses on each flap, so the
  air armor's wings, whose stroke only that marker restarts, flap on
  every Flaps press (:func:`install_wings_shim`).
- **X17** (Step 2.75d, AZ-441) ``default.xbe``, no shim, for a body
  without ``staff_center2slide`` (every one but garret4's) some clip of
  which raises its ``m_attacklevel`` marker's z above 0.01 (its own on
  water_lizardX, water_lizard, air_octopus and shadow_demon; the one B
  adds, with the tracks of the garret4 clips it bakes: every
  garret4-mode bake, the townsfolk and the clipless bodies in own mode;
  not firedrake's own, which never rises, nor B's on Balthazar, keylord,
  overlord or the elementals in own mode, whose clips don't raise it): the
  cvar ``combat/staff hits walls`` defaults to 0 (VA 0xFB9D6), so the
  staff-hits-wall sweep 0x8C8A0, which casts garret4's staff from stale
  stack bytes on such a body and ends a swing with no damage on a hit,
  never runs (:func:`sweeps_no_staff`, :func:`install_staff_walls_off`).
- **X18** (Step 2.104, AZ-525) ``default.xbe``, when the build writes a
  ``Damage multiplier`` of 1.0 or more (the balance, the damage slider,
  X10's ring) into a column whose vanilla one is under 1.0
  (:func:`light_columns`: basic1-3, right1, up1): the C shim
  ``player_model/light_hit.c`` at the hit-level chooser's compare (VA
  0x30C1C) makes the player's melee hit there level 1, a stun, as
  garret4's is, whatever its multiplier, so the combo, whose next basic
  needs a stunned target, can chain; its damage stays the multiplier's
  (:func:`install_light_hit_shim`).  So is the hit of a set's first three
  attacks (X36's, standing for basic1-3) whose column's multiplier is 1.0
  or more (Step 4.3, D1045: :func:`set_unstunned`), read from X36's state,
  so every set's combo chains on a hit, and so is X37's drain's hit there
  (its box's touch, which the game's level 2 made clear the swing's stun:
  beamlord's set 2 restarted at its drain), X37 naming its target while
  it sends it (:data:`LIGHT_DRAIN`).
- **X19** (Step 2.104, AZ-520) ``default.xbe``, when the camera point
  (X8's, or a body's own ``m_head`` at rest: Balthazar's drawn larger)
  sits above garret4's eye height (:func:`camera_plan`'s lift): the C shim
  ``player_model/eye_sweep.c`` at the level camera's sweep from its point
  to its wanted place (VA 0x810F3) tries a sweep that hits again from
  that much lower, on the line from the body's centre to the point, and
  keeps the camera's distance when that one is clear, so a tall point
  doesn't pull the camera in on geometry garret4's camera passes under
  (f3's zipline beam); its line-of-sight test (VA 0x80C35, Step 2.107)
  tries the same lowered point, so a camera kept that way isn't pulled
  in 0.8 s later for the sight of the drawn top (a1's ladder); swimming,
  the game's (:func:`install_eye_sweep_shim`).
- **X20** (Step 2.105, AZ-520) ``default.xbe``, on a body drawn taller
  than garret4 (Step 2.107: its drawn height over his above 1, at a scale
  above 0), or away from x1 one whose camera point rides under its centre
  on X9's hang (:data:`RIDE_CENTRE`): the C shim ``player_model/eye_hang.c`` where the level camera
  goes on from getting its point (VA 0x81292) raises the point to the
  body's centre while the player hangs onto or rides the zipline, or X22
  still eases it off the ride, and it hangs lower (X9 hangs the body X'
  times garret4's grab under the cable), so the camera's line-of-sight
  test and slide aim from the centre, not from under it
  (:func:`install_eye_hang_shim`).
- **X21** (Step 2.105, AZ-523) ``default.xbe``, own body, when its
  basics reach past 3.0 m (:func:`search_reach`): the C shim
  ``player_model/target_search.c`` at the transition search's CALL of
  ``attack_target_find`` (VA 0x7EF80), with that finder's seven reads of
  its 3.0 m radius pointed at the shim's own: where no target is within
  3 m the player's search in basic1-3 looks again out to the reach and
  takes a stunned or frozen target there, so the combo chains on a far
  hit (:func:`install_search_shim`).
- **X22** (Step 2.105, AZ-529) ``default.xbe``, on a body X9's ride or
  hang landings serve drawn at a model scale other than 1: the C shim
  ``player_model/hang_ease.c`` at the CALLs of 0x42E40 that place
  m_feet at the centre less 1.0 m on the let-go, a wing flap and every
  airborne tick (VAs 0x89290, 0x8944E, 0x8996D) moves the drawn body at
  most 0.847 m a placement against its centre, so letting go of the
  zipline or reaching the cable's end it eases from its hang to its
  stance instead of popping 4.5 m, and the walk's CALL of the classifier
  after its placement (VA 0x8672A) goes on with an ease a landing
  interrupts (Step 2.189b, AZ-711; :func:`install_hang_ease_shim`).
- **X23** (Step 2.106, AZ-529) ``default.xbe``, on a baked body drawn at
  a model scale other than 1: the C shim ``player_model/over_top.c`` at
  the top dismount's CALL of the state's landing 0x8C080 (VA 0x87F65,
  after its climb_up_edge setter) moves climb_up_edge's glide start
  down by (D - 1) x garret4's ``m_grab`` and its end by (D - 1) x his
  ``m_feet`` (D the drawn scale), which 0x41E50 scaled and 0x42430
  didn't, so the drawn feet go over the top onto the floor instead of
  floating 1.8-3.1 m over it and dropping (:func:`install_over_top_shim`).
- **X26** (Step 2.116, D286) ``default.xbe``, exactly where X23 is: the C
  shim ``player_model/stance_term.c`` at critter_model_matrix's CALL of
  0x402E0 (VA 0x42253) multiplies the aligned-node term by the drawn
  scale while the stance's hold is on (state 0, node m_feet, a term over
  1 mm; kept in any state while both hold), so the drawn body settles
  into its stance on the floor where X23 put it instead of popping
  (D - 1) x his ``m_feet`` up (:func:`install_stance_term_shim`); with it
  X8's point on a baked body follows the climb-over's glide and holds
  through the stance (:data:`G4_OVER_FEET`).
- **X48** (Step 2.189b, AZ-706, AZ-711) ``default.xbe``, beside X22 where
  the let-go's or a landing's crossfade takes the drawn body more than
  0.05 m past its own ground clips' lowest (:func:`fade_dip`), or, where X28
  holds the ride, past that lowest and more than 0.05 m under its origin
  (Step 2.207d): the C shim
  ``player_model/fade_floor.c`` at critter_model_matrix's CALL of
  glide_origin (VA 0x42237) raises the drawn origin, for 12 ticks after
  the player leaves the ride or lands, by however far the frame's pose
  draws its lowest weight-bearing point under the floor under the centre
  (its hair, cloth and a carried prop left out, :func:`loose_bones`), so
  a big body crossing into the fall or its stance is drawn on the floor,
  not through it nor held over it; the camera point's matrix (the CALL
  at 0x41FB0) keeps the game's origin, so the screen doesn't bob with
  the lift (Step 2.192, AZ-746) (:func:`install_fade_shim`).
- **X27** (Step 2.116, AZ-541) ``default.xbe``, when X25's rig scale is
  under 0.5 (:func:`camera_plan`'s ``near``): the C shim
  ``player_model/near_draw.c`` at the critter draw's two loads of the
  movie-mode flag (VAs 0x3EA57, 0x3EC58) gives 1 for the player, so its
  body is drawn opaque with the eye within the game's 1.0 m hide (and
  1.5 m fade) of its collision centre, which sits over a tiny body's
  drawn top (:func:`install_near_draw_shim`).
- **X25** (Step 2.107, D280) ``default.xbe``, no shim, on a body drawn at
  another size than garret4's (:func:`camera_plan`'s rig scale s, the
  drawn height over his, raised until the drawn box :func:`frames`, at
  least 0.1; installed when it is 0.005 or more off 1, at a scale above
  0): the level camera's eight metre-valued constants (the rest
  distance, the zoom's range and rate, the regrow's, the water push's
  and RT's: :data:`CAMERA_RIG`) scaled by s, the rest distance to
  5.11s - 0.11 m, so the camera frames the body as it frames garret4 at
  x1, and the regrow's stick multiply (VA 0x8196F) NOPed, so a camera
  geometry pulled in grows back at rest (:func:`install_camera_rig`).
  Installed last.
- **W14** (Step 2.69; D223, D228) ``config.xbr`` ``attacks_anims``: with
  the attack balance (on in own body), each attack column's ``Damage
  multiplier`` := garret4's x B (:func:`weigh_attacks`) x the damage
  slider (its 11 empty cells filled, as W2 fills garret4's scale), and
  the speed slider multiplies each attack's ``Rate`` (W5's, if any) but
  the roll's.
- **W19** (Step 2.104, AZ-496) ``config.xbr`` ``attacks_anims``, own
  body: basic1-3's ``Move end1`` (not a column X10 turns: its ring
  carries each clip's) chains
  :data:`CHAIN_AFTER_HIT` (0.2 s) after the move's first damage tick, or
  :data:`STUN_LAG` (4 ticks) after its box first meets a target ahead if
  that is later (Step 2.105, AZ-495: :func:`contact`, its box filled
  where X13 fills it: Step 2.106, AZ-534; Step 2.132), so the next press
  finds the target its light hit stunned already and still stunned
  (:func:`chain_point`); any other attack column but the roll, only where
  its own ``Move end1`` would chain before its move touches the target
  (Step 2.106, AZ-495: :func:`chains_early`; X10's ring by its chained
  mask).
- **W26** (Step 2.134b, D337-D339; W20's place, Step 2.106, AZ-491)
  ``characters.xbr``, every mode: a mesh group on the body's root bone
  alone that lies far from it on a body with a ``hoe`` clip (the
  townsmen farmers' hoe, carried with the pelvis 1.16 m to the right) is
  skinned to a free end joint re-parented to the right hand, which every
  baked clip keys along garret4's staff; W6 binds the staff fx to its two
  ends, and in Balanced X3's rows are the box around it: the farmers' default
  weapon, the hoe (Step 2.161a, D492-D495: weapons are data,
  :mod:`azurik_mod.patches._player_weapons`, whose :func:`loadout` says
  what a build makes of a body's weapon).
- **W22** (Step 2.137, D359) ``characters.xbr`` and ``index.xbr``, for a
  variant (``variant=``, :mod:`azurik_mod.patches._player_variants`),
  after B and W17: the markers its recipe grows (garret4's record
  defaults, at rest off) and the clips its generators make, as
  ``characters/<body>/v/<clip>``, which its recipe's columns play (W3
  writes the names); X33 (``player_model/attack_carry.c``) carries its
  ``carry`` columns along the stick too.
- **W24** (Step 2.142, D390) ``characters.xbr``, for a variant with a
  ``mesh``, before anything reads the body: its glTF's moved vertices and
  its deform ops written into the body's LOD-0 vertices in place
  (positions, and the normals of their fans; :mod:`azurik_mod.assets.mesh_edit`),
  so the size, the camera's box, the hang check and the bake measure the
  edited mesh; every species wearing the body (and their NPCs) changes
  with it, named in the build log.
- **W28** (Step 2.143, D428) ``characters.xbr``, for a variant with
  ``arms`` or a ``jiggle``: every clip the build gives the body (its own
  in place; the ones this build added, added again in their order)
  restyled (:func:`~azurik_mod.patches._player_variants.restyled`): last
  in the dress its arms turned out but in the recipe's ``v/`` clips, so
  every check after it reads them; and last in the build, once every
  rate cell is written, W29's jiggle bones keyed with their springs but
  in its ``still`` ones, each clip at the rate the game plays it
  (:func:`playback_rates`, AZ-648: her walk baked at the run slot's
  1.217 rang at 6-9 Hz in the walk slot, which plays it at 4.7-6.6). A
  clip a walk slot (8, 13) and a run slot (9, 14) both play goes to the
  run slots as a copy, ``characters/<body>/r/<clip>`` (:data:`RATE_DIR`,
  :func:`rate_copies`), so each is keyed at its own slot's rate.
- **W29** (Step 2.143, D428) ``characters.xbr``, for a variant with a
  ``jiggle``, right after W24: its leaf bones re-parented in place, its
  palette entries freed and its regions reskinned on LOD 0
  (:func:`~azurik_mod.assets.jiggle.rig`; W39 cuts its other LODs anew
  from it: garret4's shadow LOD, AZ-783).
- **W36** (Step 2.166c) ``characters.xbr`` and ``config.xbr``, after
  every write of the body's LOD 0: a one-LOD body past
  :data:`~azurik_mod.assets.decimate.SHADOW_MIN` triangles (or a recipe's
  ``lods.shadow``) takes a coarse LOD 1 that only garret4's realtime
  shadow draws (:func:`write_shadow_lod`).
- **W39** (Step 2.166d, D537's L4) ``characters.xbr`` and ``config.xbr``,
  for a variant with ``lods.ratio``, after every write of the body's LOD 0
  and before W36 (which then adds none) and W38: its LODs past LOD 0 cut
  anew from its final LOD 0 and garret4's switch distances set to its
  ``at`` (:func:`write_lods`).
- **W38** (Step 2.170b; D539, D734) ``characters.xbr`` and ``index.xbr``,
  for a variant with ``colours``, after W36 (every other write of the
  body): a copy of the body, ``characters/<body>/v/skin``, its rows
  drawing the recoloured textures
  (:func:`~azurik_mod.assets.paint.write_colours`); with it **X47**
  ``default.xbe``: ``player_model/body_key.c`` at the species bind's push
  of 'characters/%s' (VA 0x4B900) formats the copy's key for the
  player's species alone, so every NPC wearing the body keeps its own
  (:func:`install_body_key_shim`).  **P2** (Step 2.203, D543): a picked
  prop (W31-W33) or a recipe's mesh (:func:`remeshes`) on a body some
  level places a critter wearing takes the copy too, and the body's own
  entries go back to vanilla's but the bones and markers the build
  appended (:func:`~azurik_mod.assets.paint.npc_body`), so they are the
  player's alone.  A recipe on garret4's own body
  (Step 2.170c, D748) takes W38 in place after his own build: his rows
  name the recoloured textures, with no copy and no X47; since Step
  2.206 (D813) its other layers are made on his own build too
  (:func:`_garret4_recipe`, :func:`_apply_garret4`).

**Gameplay modes (D219, D225, D230; Step 2.65).**  ``mode`` picks how
much of the body's own gameplay the player takes (:data:`MODES`):

- ``garret4`` (garret4's exact; D131's standardize): W2 writes nothing
  (garret4's scale 1.0 and bounds), and **W5** scales each
  ``attacks_anims`` ``Rate`` by the length of the clip W3 picked over the
  length of garret4's clip for that column (:func:`standard_rate`), so
  each attack and the roll last garret4's time: a move lasts its window
  times its clip's length over ``Rate``.  X4 then rolls garret4's
  distance in garret4's 21 ticks, and X3 gives every body with clips
  garret4's hit box (Step 2.24f), each column garret4's own box and
  window (Step 2.68); no X10.
- ``own`` (own body, logic-safe; the default, D225): the body's own
  scale, clips and boxes, but W5 on the roll (garret4's 21 ticks) and on
  an attack so short it ends before its window can hit (:func:`attack_move`
  lands none at its Rate: garret4's time, Step 2.103, AZ-494; fire_shard's
  one-tick clips, every column),
  the **W5 wind-up band** (an attack whose damage window opens later than
  :data:`WINDUP_MAX` into its move gets the ``Rate`` that opens it then:
  :func:`windup`), **W7** the stride (garret4's ``walkAnimSpeed`` and
  ``runAnimSpeed`` := the clip its walk or run slot plays measured on his
  calibration, else the species', when nonzero; a variant's own gait,
  its ``slots``, its planted feet's speed, so they keep pace with the
  ground: :func:`stride_cells`, :func:`planted`, Step 2.171), X3 also on every
  attack whose own box can't hit a target on the ground (the reach test,
  :func:`reach_misses`, Step 2.69; X10's ring keeping the clips that
  can, :func:`hitting_ring`), X7's 0.4 s hit, and by default the
  attack balance (W14) and reach-to-ground (X13) (:data:`ATTACK_DEFAULTS`).

D230's third mode, ``full`` (fully the model's own), is retired (Step
2.129, D329): it fails by name (:data:`RETIRED_MODES`).

**Size (Step 2.68, Q304).**  ``size`` ``garret4`` scales the body, in
any mode, to garret4's height: W2 writes garret4's height over the
body's (:func:`~azurik_mod.assets.characters.height`, the top of its
mesh, or the longest side of a mesh that lies flat) as its scale
(:func:`size_scale`; kingkong's golem x 5 becomes x 0.59), and X8 aims
the camera at garret4's eye height on an upright body; ``own``, the
default, keeps the mode's scale.

**Model scale (Step 2.98, D279).**  ``model_scale`` multiplies the scale
W2 writes (the size's: the species' own, garret4's height, or 1.0 in
garret4's exact), so the body is drawn that many times its size, and
whatever the size moves follows: the body's own hit boxes (own mode's
reach test and X10 ring, the balance, reach-to-ground and the logic's
reach judge them at that scale), X8's camera point and the action point
(model units, which the game scales), the camera's rig and swim margins
(X25, Step 2.107: the camera frames the drawn body as it frames garret4
at x1), the walk clip's rate (the game's
speed over scale), ``boundRadius`` (the body's at that scale, never
under garret4's 1.5 nor 1.5 times it) and the zipline hang (X9's ride
and hang_start hang the body that many times garret4's ``m_grab`` below
the cable, a baked body that many less 1 below its own: Step 2.104,
AZ-526, :func:`needs_hang_shim`).  X3's box stays garret4's size
(on a hand, above x1, at x1's place beside the facing line:
:func:`~azurik_mod.patches._player_damage_marker.x3_side`, Step 2.103,
AZ-521), and the movement garret4's.  1.0 writes what no option writes; any
other scale is a build no sitting graded (:func:`mode_status`), but
garret4's own body at x0.5, x1.7 and x2 (Step 2.123, :data:`GARRET4_SIZES`).

The species ``garret4`` writes nothing.  A species that has no ``body``
cell or whose body has no model fails the build by name (D35, D112); the
73 items are offered, "untested" (D260, Step 2.90b, amending D112).

**Support status (D111 refined).**  Every species can be chosen; each
shows green (passes the xemu checklist), yellow (partly: the game plays
through) or red (doesn't).  :data:`SUPPORT` holds every usable species of
the vanilla disc but the 73 items (since Step 2.40, P8; the items, usable
since D260, are graded by none) and its evidence; only an xemu
sitting changes it, and a species whose build is byte-identical to a
graded one carries that grade (Q262, :data:`SAME_BUILD`; the builds with
Garret's sounds, which the sittings graded: Step 2.72).  A species it
doesn't hold (an item) is red, "untested".  Sitting q281 (Step 2.45) regraded the
earlier sittings' greens on their current builds (Q281).  Each gameplay
mode's status at each size comes from a sitting of that build
(:data:`MODE_GRADES`, Steps 2.74, 2.75; :func:`mode_status`): a mode and
size no sitting graded, and no share covers, is ``unseen`` (D242, since
Step 2.75b's sitting S4), but an item's red "untested" in garret4's
exact and own body.
"""

from __future__ import annotations

import functools
import math
import re
import statistics
import struct
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from azurkit.core import fdlibm
from azurkit.core import progress as _progress
from azurkit.tools.characters.characters import (
    CAMERA_MARKER,
    DAMAGE_MARKERS,
    FLAT,
    MELEE_REACH,
    ROOT_NODE,
    Body,
    DamageWindow,
    body_names,
    damage_anchor,
    damage_boxes,
    damage_windows,
    first_contact,
    forward,
    height,
    inverse_binds,
    marker_default,
    marker_peak,
    marker_records,
    mesh_bounds,
    mesh_points,
    moves_root,
    near,
    read_body,
)
from azurkit.tools.characters import CHAINS, DEFAULT_CHAIN
from azurkit.tools.characters import fx_edit, fx_templates
from azurkit.tools.characters import jiggle as jiggles
from azurkit.tools.characters import jiggle_rt
from azurkit.tools.characters import mesh_edit
from azurkit.tools.characters.grades import load_grades
from azurkit.tools.characters.model_chains import KINDS as CHAIN_KINDS
from azurkit.tools.characters.paint import located, npc_body, skin_key, write_colours
from azurkit.tools.characters.retarget import (
    BAKED_DIR,
    FLT_MAX,
    LIFTS as BAKED_LIFTS,
    MAPS as BAKED_BODIES,
    Clip,
    Retarget,
    Rig,
    Track,
    _aim,
    _slopes,
    _turn,
    add_clips,
    bake_body,
    bake_clip,
    centred,
    evaluate,
    named_clip,
    origins,
    pose,
    qinv,
    qmul,
    quiet,
    named_clip,
    read_clip,
    role_map,
)
from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records, parse_index_xbr
from azurkit.tools.characters.ports import xbe_layout, xbe_site
from azurkit.tools.characters.xbox_adpcm import LONGEST_WAVE, RATE as SOUND_RATE, wave_entry
from azurkit.tools.characters._player_damage_marker import (
    DAMAGE_MARKER,
    GARRET4_BOX,
    GARRET4_EXTENT,
    GARRET4_FORWARD,
    GARRET4_REACH,
    NO_BOX,
    SHIM as DAMAGE_MARKER_SHIM,
    garret4_boxes,
    garret4_window,
    install_damage_marker,
    x3_forward,
    x3_reach,
    x3_side,
)
from azurkit.tools.characters import _player_crossfade as crossfade
from azurkit.tools.characters._player_kit import (
    Style,
    carried as kit_carried,
    carry as kit_carry,
    hit_wave,
    kit_document,
    swing_waves,
)
from azurkit.tools.characters import _player_fx_ring as fx_ring
from azurkit.tools.characters import _player_throw as throws
from azurkit.tools.characters._player_borrow import (
    ANIM_CHANGE_CALL,
    FIRST as BORROW_FIRST,
    FIRST_SHIM as BORROW_FIRST_SHIM,
    HOOKS as BORROW_HOOKS,
    OBJECT as BORROW_OBJECT,
    SHIM as BORROW_SHIM,
    anim_change_return,
    borrow_table,
    install_borrow_shim,
    install_first_shim,
    needed_hooks,
)
from azurkit.tools.characters._player_slots import (
    ASKED,
    BASE_CLIPS,
    HIT,
    CALM_SEAM,
    GAIT_TWINS,
    HOOK as SLOTS_HOOK,
    IDLE_HOOK,
    IDLE_OBJECT,
    IDLE_SHIM,
    IDLE_TIMER_LOAD,
    JUMPS,
    SHIM as SLOTS_SHIM,
    TOUCHDOWN_TICKS,
    base_seam,
    calm_idle,
    fidget_mask,
    idle_fills,
    install_idle_pick,
    install_slots_shim,
    recipe_fills,
    slot_fills,
)
from azurkit.tools.characters._player_victory import (CANCEL_HOOK, CANCEL_SHIM, VICTORIES, install_victory_cancel,
                                                 victories_line, victory_copies, victory_fills)
from azurkit.tools.characters._player_weapons import (
    CAST_SWITCH,
    COPY,
    FLOAT,
    IN_PLACE,
    ON_CHAIN,
    RIGID,
    TIP_BOX,
    Carriers,
    Loadout,
    Magic,
    add_carriers,
    attack_clips,
    carried,
    carried_copy,
    carriers,
    carry_props,
    chain_lifted,
    copy_prop,
    faded_lifted,
    own_lifted,
    cast_clips,
    cast_copies,
    cut_staff,
    float_clips,
    held_window,
    hide_own,
    loadout,
    magic,
    magic_graph,
    ride,
)
from azurkit.tools.characters._player_weapons import grade as weapon_grade
from azurkit.tools.characters._player_weapons import seen as weapon_seen
from azurkit.tools.characters._player_sounds import (
    SOUND_HOOKS,
    SOUND_MODES,
    SOUNDS_SHIM,
    SOUNDS_TABLE,
    XBE_SOUND_SITES,
    SoundRoles,
    describe,
    describe_variant,
    install_xbe_sounds,
    kit_swings,
    sound_roles,
    sound_table,
    variant_roles,
    write_sound_cells,
)
from azurkit.tools.characters.ports import (
    apply_trampoline_patch,
    patch_spec_site,
    trampoline_shim_data,
    trampoline_symbol_va,
)
from azurkit.tools.characters.ports import ShimSource
from azurkit.tools.characters.ports import release_session
from azurkit.tools.characters.ports import CHECKOUT
from azurkit.tools.characters.ports import (
    BytesParam,
    FloatParam,
    PatchSpec,
    TrampolinePatch,
    finite_slider_value,
    pack_f32,
)
from azurkit.core.xbe import resolve_va_to_file
from azurkit.tools.characters.ports import _load_doc_for_edit
from azurkit.tools.characters.ports import XbrDocument
from azurkit.core.xbr.append import NewResource, append_resources
from azurkit.tools.characters.ports import (
    XbrStructuralError,
    clear_keyed_cell,
    point_keyed_string,
    replace_bytes_at,
    set_keyed_double,
    set_keyed_string,
    string_sharer_counts,
)
from azurkit.core.xbr.graph import Euler, bind_name, list_at, local_matrix, lstr, record_offsets
from azurkit.core.xbr.nodes import named_resources, parse_toc

PLAYER = "garret4"
"""The player's species: the only one with a PlayerControl (D112)."""

_SITTINGS = "xemu sittings modelswap and modelswap2, 2026-10-12"
SUPPORT: dict[str, tuple[str, str]] = {
    "garret4": ("green", f"the vanilla player, the control of {_SITTINGS}"),
}
_P8 = "xemu sitting p8, 2026-10-13"
SUPPORT |= {
    "guard_earth": ("yellow", "plays through with X4, X3 and X7, but none of its attacks dealt "
                              "damage (no contact in 10) and its 12.4 m body fills the lower half "
                              f"of the screen ({_P8})"),
    "water_tentacle2": ("yellow", "plays through with X4 and X7, its attacks dealing damage, but its "
                                  f"roll takes 197 ticks (6.6 s) at its own clip speed (Q265; {_P8})"),
    "water_tentacle3": ("yellow", "plays through with X4 and X7, its attacks dealing damage, but its "
                                  f"roll takes 197 ticks (6.6 s) at its own clip speed (Q265; {_P8})"),
    "magmar": ("yellow", "plays through with X4 and X7, its attacks dealing damage, but its roll "
                         f"takes 73 ticks (2.4 s) at its own clip speed ({_P8})"),
    "kingkong": ("yellow", "plays through with X4 and X7 at scale 5 (golem's body), its attacks "
                           f"dealing damage, but its body fills the screen and hides the way ahead ({_P8})"),
    "boulder": ("green", f"passes the checklist with X4, X3 and X7; it attacks with its run clip ({_P8})"),
    "overlord and golem": ("green", f"passes the checklist with X4 and X7 at scale 1.25 ({_P8})"),
    "air_octopus": ("green", f"passes the checklist with X4 and X7; its roll takes 49 ticks ({_P8})"),
    "barnacle": ("green", f"passes the checklist with X4 and X7; its roll takes 59 ticks ({_P8})"),
    "bird": ("green", f"passes the checklist with X4, X3 and X7; a small body, 0.29 m tall ({_P8})"),
    "guard_water": ("yellow", "plays through with X4, X3 and X7, its attacks dealing damage, but its "
                              f"roll takes 73 ticks (2.4 s) at its own clip speed ({_P8})"),
    "water_tentacle1": ("yellow", "plays through with X4 and X7, its attacks dealing damage, but its "
                                  f"roll takes 215 ticks (7.2 s) at its own clip speed (Q265; {_P8})"),
    "bot": ("yellow", "plays through with X4 and X7, but none of its attacks dealt damage (no contact "
                      f"in 10) and its roll takes 71 ticks (2.4 s) ({_P8})"),
    **dict.fromkeys(("channeler", "town_female_4"), (
        "red", "frozen in its bind pose at each level start until its first roll, attack or hit, having "
               "no idle, walk or run clip for X6 to start (AZ-303's kind); then its roll clip loops in "
               f"every state ({_P8})")),
    "firefly": ("yellow", "plays through with X4, X3, X6 and X7, but its body is a speck the camera "
                          f"barely shows ({_P8})"),
    "fish_little1": ("yellow", "plays through with X4, X3 and X7, but its body is a speck the camera "
                               f"barely shows ({_P8})"),
    "fish_little2": ("yellow", "plays through with X4, X3 and X7 at scale 2, but its body is a speck "
                               f"the camera barely shows ({_P8})"),
    "blaze_sentinel": ("green", f"passes the checklist with X4 and X7 ({_P8})"),
    "fire_bot": ("green", f"passes the checklist with X4 and X7 at scale 1.5 ({_P8})"),
    "catalisk_baby": ("green", f"passes the checklist with X4 and X7 at scale 0.5; its roll takes 53 ticks ({_P8})"),
    "fish_big": ("green", f"passes the checklist with X4, X3 and X7 ({_P8})"),
    "fire_shard": ("red", "its roll lasts 1 tick and goes nowhere at its own clip speed (Q265), none of "
                          f"its attacks dealt damage (no contact in 10), and its body is a speck ({_P8})"),
    "splinter": ("yellow", "plays through with X4 and X7 at scale 0.75, but none of its attacks dealt "
                           f"damage (no contact in 10) and its body is a speck the camera barely shows ({_P8})"),
    **dict.fromkeys(("town_child_farmer_1", "town_child_farmer_2", "town_child_farmer_3"), (
        "yellow", "plays through with X4, X3 and X7 at scale 1.15, its attacks dealing damage, but its "
                  f"roll takes 73 ticks (2.4 s) at its own clip speed ({_P8})")),
    "ice_shard": ("green", f"passes the checklist with X4 and X7; its roll takes 53 ticks ({_P8})"),
    "rock_shard": ("green", f"passes the checklist with X4 and X7; its roll takes 53 ticks ({_P8})"),
    "shard": ("green", f"passes the checklist with X4 and X7; a small body, 0.5 m tall ({_P8})"),
    "sleeth_momma": ("green", f"passes the checklist with X4 and X7 at scale 2.5 ({_P8})"),
    "town_child_2": ("green", f"passes the checklist with X4, X3 and X7 at scale 1.15 ({_P8})"),
    "town_child_3": ("green", f"passes the checklist with X4, X3 and X7 at scale 1.15 ({_P8})"),
    **dict.fromkeys(("town_girlchild_farmer_1", "town_girlchild_farmer_2"), (
        "yellow", "plays through with X4, X3 and X7 at scale 1.15, its attacks dealing damage, but its "
                  f"roll takes 73 ticks (2.4 s) at its own clip speed ({_P8})")),
    **dict.fromkeys(("town_female_1", "town_female_2", "town_girlchild_1", "town_girlchild_2"), (
        "green", f"passes the checklist with X4, X3 and X7 at scale 1.15 ({_P8})")),
    **dict.fromkeys(("town_male_1", "town_male_2", "town_male_3", "town_male_4", "town_male_5",
                     "town_male_7", "town_male_8", "town_male_9"), (
        "green", f"passes the checklist with X4, X3, X7 and X6 at scale 1.15 ({_P8})")),
    **dict.fromkeys(("town_male_farmer_1", "town_male_farmer_2", "town_male_farmer_3", "town_male_farmer_4",
                     "town_male_farmer_5", "town_male_farmer_6"), (
        "green", f"passes the checklist with X4, X3 and X7 at scale 1.15; its roll takes 53 ticks ({_P8})")),
    # D132: the clipless bodies stay selectable and red
    **dict.fromkeys(("gargoylestone", "tesla_tree"), (
        "red", "its body has no clips: the roll and the attacks never start, and it moves as a "
               f"statue ({_P8})")),
    # Q281's regrade (sitting modelswap3 graded both red on d78faf3)
    "town_male_6": ("green", "passes the checklist with X4, X3, X7 and X6 at scale 1.15: X6 starts "
                             f"each level on its walk, so it no longer shows its bind pose ({_P8})"),
    "guard_air": ("yellow", "plays through with X4, X7 and X8, the camera framing its body, but its "
                            "80-tick attacks rarely deal damage: a hit cut short all 10 here, and 4 "
                            f"of 10 dealt damage in sitting sight222kl ({_P8})"),
}
_Q281 = "xemu sitting q281, 2026-10-13"
# Q281's regrade: the greens sittings modelswap, modelswap2 and modelswap3 graded, whose builds X3's hit-reaction
# test (Step 2.22h) or X7's end of the crossfade (Step 2.22l) changed since, on their builds at 04ce3b7
SUPPORT |= {
    "keylord": ("green", "passes the checklist with X4 and X7 at scale 2; its idle clip doesn't come back "
                         f"after an action (modelswap), cosmetic ({_Q281})"),
    "flicken": ("green", "passes the checklist with X4, X3 and X7: X3's hit box makes its attacks deal "
                         f"damage ({_Q281})"),
    "air_elemental": ("green", "passes the checklist with X4 and X7; its wings span the screen below the way "
                               f"ahead ({_Q281})"),
    "water_elemental": ("green", f"passes the checklist with X4 and X7 at scale 1.2 ({_Q281})"),
    "evil_noreht": ("green", f"passes the checklist with X4 and X7 ({_Q281})"),
    "balthazar": ("green", "passes the checklist with X4 and X7; its jump attack plays attack_3, which deals "
                           f"damage ({_Q281}); since Step 2.24f the staff's particles come from his hands (W6) "
                           "and the jump attack plays attack_1 in 23 ticks, its hit box at his swinging hand "
                           "(xemu sitting x224f, 2026-10-15)"),
    "harvester": ("green", "passes the checklist with X4 and X7; its idle clip doesn't come back after an action "
                           f"(modelswap), cosmetic ({_Q281})"),
    "skrit_water": ("green", f"passes the checklist with X4, X3 and X7 ({_Q281})"),
    "overlord": ("green", "passes the checklist with X4 and X7 at scale 1.25; its own hit box sits short, so its "
                          "attacks deal damage at 0.9 m but not at 1.4 m, and its idle clip doesn't come back after "
                          f"a run (modelswap3), cosmetic ({_Q281})"),
    "fire_elemental": ("green", f"passes the checklist with X4 and X7; its roll takes 34 ticks ({_Q281})"),
    "town_child_1": ("green", "passes the checklist with X4, X3 and X7 at scale 1.15; a hit plays its idle, and it "
                              f"has no death clip (modelswap3) ({_Q281})"),
    "shadow_demon": ("yellow", "plays through with X4 and X7, its attacks dealing damage, but its translucent "
                               f"body (its own alpha) is one the camera barely shows ({_Q281})"),
    "spideyzar": ("green", "passes the checklist with X4 and X7 at scale 1.5, its body filling the lower screen "
                           "below the way ahead; a run plays its idle, and it has no death clip (modelswap3) "
                           f"({_Q281})"),
    "catalisk": ("green", f"passes the checklist with X4 and X7; its roll takes 53 ticks ({_Q281})"),
    "good_noreht": ("green", f"passes the checklist with X4, X3 and X7; a run plays its idle (modelswap3) ({_Q281})"),
    "golem": ("green", "passes the checklist with X4 and X7 at scale 1.25; a run plays its idle (modelswap3) "
                       f"({_Q281})"),
    "sleeth": ("green", "passes the checklist with X4 and X7 at scale 1.25; a run plays its idle (modelswap3) "
                        f"({_Q281})"),
    "town_female_3": ("green", "passes the checklist with X4, X3 and X7 at scale 1.15; a run and a hit play its "
                               f"idle, and it has no death clip (modelswap3) ({_Q281})"),
    "overlord and gargoyle": ("green", "passes the checklist with X4 and X7; it moves on its idle, having no walk or "
                                       f"run clip, and its wings span the screen below the way ahead ({_Q281})"),
    "firedrake": ("green", "passes the checklist with X4 and X7; it hovers low and moves on its idle, its wings "
                           f"spanning the screen below the way ahead ({_Q281})"),
    "guard_fire1": ("green", "passes the checklist with X4, X3 and X7; it hovers, X8 framing its head, and a run "
                             f"plays its idle (modelswap3) ({_Q281})"),
}
SAME_BUILD: dict[str, tuple[str, str]] = {
    "air_elemental_boss": ("air_elemental", "339663fd863a"),
    "flicken of peril": ("flicken", "7c59d41f9140"),
    "harvester_train": ("harvester", "02d11f3e51d4"),
    **dict.fromkeys(("skrit_air", "skrit_earth", "skrit_fire"), ("skrit_water", "1e96633cde91")),
    **dict.fromkeys(("cat_dead", "catalisk_grp"), ("catalisk", "080da7fc0db5")),
    "24hr": ("good_noreht", "798ffc5db115"),
    "town_child_sleep": ("town_child_1", "67054c16b60f"),
    "town_female_3B": ("town_female_3", "c297289266a5"),
    **dict.fromkeys(("guard_fire2", "guard_fire3"), ("guard_fire1", "4886af98af81")),
    **dict.fromkeys(("town_male_6B", "town_male_sleep"), ("town_male_6", "78388e59e772")),
    "guard_air_clone": ("guard_air", "a8d4d6dff3b1"),
    "blaze_move": ("blaze_sentinel", "31eab0917b6c"),
    "catalisk_baby_grp": ("catalisk_baby", "cd05a6d36fca"),
    **dict.fromkeys(("lava_shard", "rock_shard_boss", "rock_shard_grp"), ("rock_shard", "5832e574dc5e")),
    "sleeth_x": ("sleeth_momma", "adb89fdadb51"),
    "town_female_sleep": ("town_female_4", "4020e6276002"),
    "town_girlchild_sleep": ("town_girlchild_1", "5a33f58a33b7"),
    "town_male_stand": ("town_male_3", "54ac82dd0912"),
    "tesla_tree_x": ("tesla_tree", "87a0f683d01a"),
}
"""Q262 revised (default taken under D115): a species whose build is
byte-identical to a graded one carries its grade, ``{species: (the graded
species, the whole-ISO sha256[:12] both built under the G3 recipe on the
graded sitting's code)}`` [verified 2026-10-12: every usable species built
by ``tests/_randomize_driver`` on ``d78faf3`` and on Step 2.22j's
``c17a5cc``; and 2026-10-13 on sitting p8's ``ddce363`` and sitting
q281's ``04ce3b7``, which build every usable species' ISO alike].
These are :data:`SUPPORT`'s pairs, on the code those sittings graded; a
mode's grade carries by :data:`MODE_SHARES` (AZ-492)."""
SUPPORT |= {species: (SUPPORT[graded][0],
                      f"builds the same ISO as {graded}, byte for byte, so it carries "
                      f"{graded}'s grade (Q262; on the code the sitting graded, both built "
                      f"sha256 {sha}…)")
            for species, (graded, sha) in SAME_BUILD.items()}
"""Each graded species' status (green, yellow or red) and why, from the
xemu checklist (``docs/PATCHES.md`` § "Player model swap").  A status is
the species' (Q262), or shared with a graded species whose build is
byte-identical (:data:`SAME_BUILD`; with ``sounds="garret4"``: a
species' own sounds, Step 2.72, aren't on the checklist); same body and
scale alone isn't enough.  Since Step 2.75b's sitting S4 no mode's
status shows it (D242, :func:`mode_status`): it names the species the
earlier sittings graded, on builds no mode makes exactly."""

UNTESTED = ("red", "untested")
REFUSED = "refused"

MODES = ("garret4", "own")
"""The gameplay modes (D219): garret4's exact and own body (logic-safe)."""
RETIRED_MODES = {"full": "full is retired (Step 2.129, D329): use own (Balanced, the default)"}
"""Each retired mode and what replaces it: D230's fully the model's own
fails by name in the CLI, the MCP tools and :func:`apply_player_model`."""
DEFAULT_MODE = "own"
"""A swapped model's default mode (D225)."""
MODE_NAMES = {"own": "own body", "garret4": "garret4's exact"}
"""Each mode as the build log and the GUI name it."""
MODE_ANIMS = {"garret4": "garret4", "own": "garret4"}
"""Each mode's X11 rule when no ``missing_anims`` is asked for (Step
2.73a): garret4's (D226, D229).  A body with no clips takes garret4's
in every mode, whatever is asked, his clips baked as timers its only
ones (B, X12)."""
SIZES = ("own", "garret4")
"""The size options (Step 2.68): the mode's own scale, or garret4's height."""
DEFAULT_SIZE = "own"
"""A swapped model's default size (Q304)."""


def _mode_grades() -> dict[tuple[str, str], dict[str, tuple[str, str]]]:
    """:data:`MODE_GRADES` from ``assets/mode_grades.json`` (Step X.85),
    one grade a line: each mode and size's species' grades in the file's
    order (an unknown mode or size fails by name)."""
    grades: dict[tuple[str, str], dict[str, tuple[str, str]]] = {(mode, size): {} for size in SIZES
                                                                 for mode in MODES}
    path = Path(__file__).resolve().parent / "mode_grades.json"
    for (mode, size, species), graded in load_grades(path, ("mode", "size", "species")).items():
        grades[mode, size][species] = graded
    return grades


MODE_GRADES: dict[tuple[str, str], dict[str, tuple[str, str]]] = _mode_grades()
"""Each mode's grades at each size from a sitting of that build (Steps
2.74, 2.75): ``{(mode, size): {species: (green, yellow or red, why)}}``,
which win over :data:`SUPPORT`'s; a :data:`SAME_BUILD` species carries
its partner's (Q262, D242).  Sitting x275a (Step 2.75a, on the stack
before the bake) graded bodies the bake doesn't map.  Their builds have
changed since only in X12's object (Step 2.89 dropped its by-name remap,
which never ran on them: they borrow no garret4 clip) and so in where
the later shims land; their game files are the same, so the grades
stand [inferred static; Step 2.75b's sitting runs the current builds].
Sitting 2.75c (Step 2.75c, the stack's top with the bake) regraded
flicken in both modes (the ladder, a hard landing, the hang and the
wings now pass; spideyzar, water_tentacle1 and the two sized bodies
landed hard in garret4's 13 ticks too) and saw guard_earth's ground
swings hit, its body still filling the screen; no sitting had seen a
hoist (AZ-393, flagged on every build).  Step 2.75b grades own body
for every species and garret4's exact on a sample (D242): its sitting
S1 (main's ``71f13956``, census B0's ISOs) graded the bake's headline
bodies in own body and Balthazar in garret4's exact, and saw every one
hoist at the owner's X.35 ledges where garret4 does, kingkong
own's hoist short (AZ-489) (its report, with its skeptic's re-read:
town_male_1 and town_girlchild_farmer_1 green).
Its sitting S2 (main's ``8ec856f7``, the same census ISOs) graded the
other baked townsfolk and twelve unbaked bodies in own body, and saw
nine of those hoist short (AZ-489) (its report, with its skeptic's
re-read: the three water tentacles yellow, their bodies out
of frame); its victories stay unseen.  Its sitting S3 (main's
``c21d51a0``, the same census ISOs) graded the other 31 unbaked bodies
in own body, so every own-body status is a sitting's, and saw 29 of
them hoist short (AZ-489) (its report, with its skeptic's re-read:
catalisk_baby yellow, nothing of it in frame at rest in the
water; town_child_farmer_1 green, its ground swing landing).  Its
sitting S4 (main's ``0334b2e4``, the same census ISOs) graded garret4's
exact on 14 bodies and 9 at garret4's height, so a mode and size it
left is unseen (D242); every unbaked body there but the water tentacles
hoists short, as in own body (AZ-489).  It saw S3's left rows: a victory (the request written)
plays baked in garret4's time and ends at once on a body without
victory clips (AZ-444), and town_child_farmer_2's ground swings land
(its report, with its skeptic's re-read: water_tentacle1
green at garret4's height, its swim's 19 surface switches one dip
counted unscaled; water_tentacle3 yellow there, its first basic1 hit
at swing tick 33).  Sitting 2.96 (Step 2.96, on AZ-489's fix,
``4ac5243f``; its report, with its skeptic's re-read) saw every short hoist S1-S4 found, in each mode and
size and on Europe's golem own, hold 0x100 in garret4's time (88-89
ticks against his 89: a float32 rate crossing a tick early) from his
window, with his rise, on his spot; firefly own's ladder, over the top,
down edge, hard landing, hang and step up match the control's.  Those
builds differ from the graded ones in X9's object and its six landings
alone, so each grade's other checks stand [inferred static]; a grade
whose one reason was the short hoist is green.  Sitting 2.101 (Step
2.101, main's ``2ddf6818``; its report, with its skeptic's re-read) saw Europe's golem own go
over the top in garret4's 70 ticks, ending on the control's spot
(AZ-442): golem own is green.
Sitting 2.103 (Step 2.103's fixes; its report, with its skeptic's
re-read) saw flicken own's victories
and use play its idle in garret4's time with his hit timer (AZ-444),
and fire_shard own's swings land in his time (AZ-494); it stays
yellow, a speck.
Sitting 2.104 (Step 2.104's fixes; its report, with its skeptic's
re-read) saw own body's
light hits stun at any multiplier (X18, AZ-525) and its basics chain
inside the stun (W19, X10's ring: AZ-496, AZ-523), so guard_water's,
guard_fire1's, guard_air's, town_male_farmer_1's, magmar's and
rock_shard's combos pass basic1 to a finisher, and magmar's attacks
open by swing tick 30 (AZ-524); no grade changes colour, each yellow
keeping another reason (a long lone press, its body in frame, AZ-491,
AZ-495).  Sitting 2.105 (Step 2.105's fixes; its report, with its
skeptic's re-read) saw
golem own chain onto a sentinel stunned 3.6 m out (X21, AZ-523),
guard_air own chain onto its stunned target 4 ticks after its swing
meets it (W19, AZ-495) and rock_shard's drops read as the game's
facing rule; no grade changes colour (guard_air keeps AZ-495's late
hits and short columns, rock_shard its long lone press).  Sitting
2.106 (Step 2.106's fixes; its report, with its skeptic's re-read) saw the farmers' hoe in
their hands (W20, AZ-491), so town_male_farmer_1 and _2 are green,
and guard_air own's side columns chain after their hit (W19, AZ-495);
it stays yellow for its late hits.  Step 2.117's look checks (D284:
xemu pictures judged by agents, each verdict checked by a judge seat)
saw the hoe in
town_male_farmer_3 to 6's hands too, so all six farmers are green.
Step 2.117b's re-runs of its 8 unsure passed 6 and change no colour: fire_shard
own stays yellow, its body drawn only as a shadow on the ground at
X25's 0.79 m (AZ-541).  Sitting 2.121 (Step 2.121, D299, D300;
each verdict checked by a judge seat) saw W21's victories hold state 0x100 garret4's 71-159
ticks on his clip lengths: the bodies' own on guard_water, spideyzar,
rock_shard, good_noreht, evil_noreht, splinter, guard_air and Europe's
golem own (AZ-560); no grade changes colour.  The retired fully its
own's grades went with it (Step 2.129, D329).  One grade a line in
``assets/mode_grades.json`` (Step X.85; :mod:`azurik_mod.assets.grades`)."""
MODE_SHARES: dict[tuple[str, str], dict[str, tuple[str, str, bool]]] = {
    ("own", "own"): {
        "blaze_move": ("blaze_sentinel", "117c8d648f73", True),
        "cat_dead": ("catalisk", "5aa90839ad91", True),
        "catalisk_grp": ("catalisk", "5aa90839ad91", False),
        "catalisk_baby_grp": ("catalisk_baby", "cb117933e41c", False),
        "flicken of peril": ("flicken", "d72a7c4d1403", True),
        "guard_air_clone": ("guard_air", "780f4c20f1a9", False),
        "harvester_train": ("harvester", "e1d46a25608a", True),
        "rock_shard_boss": ("rock_shard", "b3f186e3bb2b", True),
        "rock_shard_grp": ("rock_shard", "b3f186e3bb2b", False),
        **dict.fromkeys(("skrit_air", "skrit_earth", "skrit_fire"), ("skrit_water", "721138c2e1a8", False)),
        "sleeth_x": ("sleeth_momma", "af7a36fbbbdd", True),
        "tesla_tree_x": ("tesla_tree", "73e90d61ddfa", False),
        "town_child_sleep": ("town_child_1", "81dc90a68a03", False),
        "town_female_3B": ("town_female_3", "21fb9dee575d", False),
        "town_female_sleep": ("town_female_4", "0a03c4da3aff", False),
        "town_girlchild_sleep": ("town_girlchild_1", "a83ff24a2807", False),
        "town_male_stand": ("town_male_3", "55e7747b2e2d", False),
        "town_male_sleep": ("town_male_6", "e98b745369b4", False),
    },
    ("garret4", "own"): {
        "air_elemental_boss": ("air_elemental", "bb9487071a60", False),
        "blaze_move": ("blaze_sentinel", "62431344e5f3", True),
        **dict.fromkeys(("cat_dead", "catalisk_baby", "catalisk_baby_grp"), ("catalisk", "9927a06782ff", True)),
        "catalisk_grp": ("catalisk", "9927a06782ff", False),
        "flicken of peril": ("flicken", "1868054e7b45", True),
        "24hr": ("good_noreht", "3a6961490eb1", True),
        "guard_air_clone": ("guard_air", "25117c4cd1b4", False),
        **dict.fromkeys(("guard_fire2", "guard_fire3"), ("guard_fire1", "1a33b5963637", False)),
        "harvester_train": ("harvester", "72fed511a5d5", True),
        "rock_shard_boss": ("rock_shard", "c5d12f8cc9ef", True),
        "rock_shard_grp": ("rock_shard", "c5d12f8cc9ef", False),
        **dict.fromkeys(("skrit_air", "skrit_earth", "skrit_fire"), ("skrit_water", "743fcbdefcab", False)),
        "sleeth_x": ("sleeth_momma", "0f916327b085", True),
        "tesla_tree_x": ("tesla_tree", "f7177785fc09", False),
        "town_child_sleep": ("town_child_1", "abf8a7a23683", False),
        "town_female_3B": ("town_female_3", "35843a048767", False),
        "town_female_sleep": ("town_female_4", "2a16849b5d49", False),
        "town_girlchild_sleep": ("town_girlchild_1", "33842af83e1a", False),
        "town_male_stand": ("town_male_3", "522bf31c5925", False),
        **dict.fromkeys(("town_male_6B", "town_male_sleep"), ("town_male_6", "47e5daa653e7", False)),
    },
    ("own", "garret4"): {},
    ("garret4", "garret4"): {},
}
"""Q262 per mode and size (D242, AZ-492): ``{(mode, size): {species:
(partner, the whole-ISO sha256[:12] both build, sounds_only)}}``, a
species whose build in that mode and size is byte-identical to its
partner's with Garret's sounds (``--player-character-sounds garret4``:
a species' own sounds, Step 2.72, aren't on the checklist), so it
carries the partner's :data:`MODE_GRADES` grade there; ``sounds_only``:
their default builds differ in those sounds alone.  From Step 2.75b's
census B0 (``71f13956``, every usable species in each mode with both
sounds; its census table):
own body splits 24hr, guard_fire2 and 3, town_male_6B and lava_shard
from their :data:`SAME_BUILD` partners (their own stride, W7), which
garret4's exact joins again, with catalisk_baby to catalisk
and kingkong to golem.  B0 built no pair at garret4's size, so none
shares there.  Each later sitting's recheck held (sitting S4's on
``0334b2e4``, its census table of 546 rows; sitting
2.96's on AZ-489's fix, whose X9 ISOs no longer hash as these: its
census table).
Step 2.132's X32 (D333) split the pairs whose NPCs hit with different
damage records, so their hits show different effects: air_elemental_boss
(wind_2) and sleeth_x (sleeth) in both modes, and in garret4's exact
kingkong (golem's golem), catalisk_baby and its group (catalisk_baby)
and lava_shard (rock_shard's rock_shard); since Step 2.180 (D700) every
body X32 serves shows one flash, which joins sleeth_x again in both
modes and air_elemental_boss and catalisk_baby(_grp) in garret4's exact
(kingkong, lava_shard and air_elemental_boss in own body still differ:
Step 2.180's pair check);
the hashes kept are the census's, from before X32."""
UNSEEN = ("unseen", "no sitting has graded its build in this mode and size (D242)")
"""The status of a species no sitting graded in a mode and size, and no
share covers there (D242)."""
_X2123 = "xemu sitting 2.123 and its re-run, 2026-10-20"
_G4_SIZE = ("his hits reach x{s} as far (the box 2.7735 m x {s}, f1's flameSpout15 opened inside it and not past it), "
            "and he climbs over a1's ladder's top onto the floor, hangs from f3's zipline at x{s} his grab and runs, "
            "jumps and runs off a ledge as at x1")
GARRET4_SIZES: dict[float, tuple[str, str]] = {
    0.5: ("yellow", _G4_SIZE.format(s=0.5) + f" ({_X2123})"),
    1.7: ("yellow", _G4_SIZE.format(s=1.7) + f" ({_X2123})"),
    2.0: ("yellow", _G4_SIZE.format(s=2) + f" ({_X2123})"),
}
"""garret4's own body's status drawn at the Model sizes a sitting graded
(Step 2.123; D242: any other size is unseen); the attack sliders keep
it, as a swapped body keeps its grade with them."""


def drawn_scale(sized: float | None, mode: str, own: float | None, model_scale: float) -> float:
    """The scale the game draws a swapped body at (its +0x188): W2's
    scale cell, ``sized`` (:func:`size_scale`, size ``garret4``) or else
    the species' own ``scale`` (``own``; garret4's 1 in mode ``garret4``),
    times the model scale."""
    scale = sized if sized is not None else None if mode == "garret4" else own
    return (1.0 if scale is None else scale) * model_scale


def body_scale(characters_xbr: bytes, body: Body, row: dict, mode: str, size: str
               ) -> tuple[float | None, float | None]:
    """(sized, scale) of a swapped ``body`` whose critters_engine ``row``
    is the species': with ``size`` garret4 the scale that stands it at his
    height (:func:`size_scale`; ``None``: its own size), and the scale W2
    writes at Model size 1 (that one, else none in mode ``garret4``,
    else the species' own cell; ``None``: none written, drawn x1)."""
    sized = size_scale(characters_xbr, body) if size == "garret4" else None
    return sized, sized if sized is not None else None if mode == "garret4" else row["scale"]


def size_scale(characters_xbr: bytes, body: Body) -> float | None:
    """The scale that stands ``body`` at garret4's height: garret4's
    :func:`~azurik_mod.assets.characters.height` (2.002 m, the top of his
    mesh) over the body's, or ``None`` for a body with no height to
    measure."""
    tall = height(characters_xbr, body)
    return height(characters_xbr, read_body(characters_xbr, PLAYER)) / tall if tall > 0.0 else None


def eye_height(characters_xbr: bytes) -> float:
    """garret4's eye height in metres: where his ``m_head`` (the camera
    point) rests, 1.9925 m."""
    return marker_default(characters_xbr, PLAYER, CAMERA_MARKER)[2]


WINDUP_MAX = 1.0
"""Own mode's wind-up band (Q304, D225): the latest a damage window may
open into an attack move, in seconds."""
X3_OPENS = 0.2
"""When X3's damage marker comes on, as a fraction of the move
(``player_model/damage_marker.c``: 20% to 50%)."""
X3_CLOSES = 0.5
"""When X3's damage marker goes off, as a fraction of the move."""
HIT_REACH = 0.6
"""Own mode's reach test (Step 2.69, replacing Step 2.65's interim list of
four): an attack's own box must reach this far (m) from the feet to hit
a target in front of the player (X13's fill bringing every box ahead
back to the feet, the facing line and the floor: Step 2.132).  The sittings put the line between
0.49 and 0.78 m: in p8 shard's 0.78 m box dealt damage (4 hits in its
jump-attack cycles) and splinter's 0.43 m and fire_shard's 0.49 m made
no contact in 10; in q281 overlord's 0.97 and 1.06 m boxes hit at 0.9 m.
A short box that clears it keeps its own reach (D222 amended), bumped
x1.25 by the balance (:data:`REACH_BUMP`)."""
HIT_NEAR = GARRET4_REACH
"""How near (m) to the feet X3's box at the action point must come to
hit a target in front of the player (Step 2.70b, :func:`x3_anchor`):
within garret4's basic swing, 2.77 m.  A giant's box reaches far and
can still pass over everything near it: guard_earth's X3 box, at its
hand 6.5-8.5 m ahead through X3's window, came no nearer than 5.4 m and
touched no e7 enemy in sitting 2.75a's ground swings, while spideyzar's
attack_2, 1.0 m off at its nearest, dealt damage there; the line between
is unmeasured (default taken under D115: garret4's own reach, D237)."""
NO_CONTACT = frozenset({"bot"})
"""The bodies whose own box a sitting saw make no contact although the
reach test passes it: own mode gives each of their attacks X3.  p8:
bot's 1.11 m box, which reaches 1.0 m ahead through 0.2 s of its clip,
made no contact in 10 (the one of Step 2.65's interim list of four the
reach test can't tell)."""
_STRIDE = ("walkAnimSpeed", "runAnimSpeed")
STRIDE_SLOTS = (8, 9)
"""The base clip slots (walk, run) whose clip 0x30D90 plays at the speed
over (the drawn scale x ``walkAnimSpeed``, ``runAnimSpeed``)."""
STRIDE_HZ = 240.0
"""How often :func:`stride` samples a clip, per second."""
STANCE_BAND = 0.03
"""A foot is in its stance within this share of the body's bind height
of its lowest point in the clip (:func:`stride`)."""
STRIDE_CADENCE = (0.5, 2.0)
"""The strides per second (a clip's :func:`stride` over its bind height)
a walk or run clip of a body's own measures within, as a share of
garret4's for that slot, for W7 to calibrate by it (:func:`stride_cells`):
a floating body's feet plant nowhere (the elementals', 0.01-0.06)."""
_FEET = ("foot", "toe", "ankle", "heel")


def stride(characters_xbr: bytes, body: str, clip: str) -> tuple[float, float] | None:
    """How fast ``body``'s ``clip`` strides (Step 2.133, AZ-610; the
    read-game's bone-origin measure): (its foot bones' mean backward speed,
    model units a second at rate 1, over the samples at :data:`STRIDE_HZ`
    in which each is within :data:`STANCE_BAND` of the bind height of its
    own lowest point, averaged over the bones named foot, toe, ankle or
    heel with 5 such samples or more; the body's bind height), ``None``
    with no such foot or clip."""
    try:
        rig, motion = Rig.read(characters_xbr, body), named_clip(characters_xbr, body, clip)
    except ValueError:
        return None
    return _stride(rig, motion)


@functools.lru_cache(maxsize=256)
def _stride(rig: Rig, motion: Clip) -> tuple[float, float] | None:
    """:func:`stride` of ``motion`` on ``rig`` (garret4's two clips are measured once a process)."""
    n = int(motion.length * STRIDE_HZ)
    feet = [k for k, bone in enumerate(rig.bones) if any(w in bone.name.lower() for w in _FEET)]
    tall = max(p[2] for p in rig.positions) - min(p[2] for p in rig.positions)
    if n < 2 or not feet or tall <= 0.0:
        return None
    at = [origins(rig, motion, i / STRIDE_HZ) for i in range(n + 1)]
    speeds = []
    for k in feet:
        low = min(p[k][2] for p in at)
        stance = [i for i in range(n) if at[i][k][2] - low <= STANCE_BAND * tall]
        if len(stance) >= 5:
            speeds.append(sum(at[i][k][1] - at[i + 1][k][1] for i in stance) * STRIDE_HZ / len(stance))
    return (statistics.mean(speeds), tall) if speeds else None


PLANT_BAND = 0.005
"""A foot is planted within this share of the body's bind height of its
lowest point in the clip (:func:`planted`): a tight band, so a foot on its
way up or down isn't counted (the 3% of :data:`STANCE_BAND` reads garret4's
walk 1.4 times slower than his planted foot moves: the 2.171 design's
``stance_detail``)."""
PLANT_MIN = 0.05
"""The least planted speed (:func:`planted`) of a gait a recipe's ``slots``
names, as a share of its body's bind height a second (:func:`gait_checks`):
town_female_2's walk 0.30, her idles 0.001-0.002."""


def planted(characters_xbr: bytes, body: str, clip: str) -> float | None:
    """How fast ``body``'s ``clip`` moves its planted feet back (Step
    2.171, D440: a gait timed so its feet keep pace with the ground): the
    median backward speed (model units a second at rate 1) of each bone
    named foot, toe, ankle or heel over the samples at :data:`STRIDE_HZ`
    in which it is within :data:`PLANT_BAND` of the body's bind height of
    its own lowest point, averaged over the bones with 5 such samples or
    more; ``None`` with no such foot or clip.  A gait played back in time
    gives its forward clip's less."""
    try:
        rig, motion = Rig.read(characters_xbr, body), named_clip(characters_xbr, body, clip)
    except ValueError:
        return None
    return _planted(rig, motion)


def bind_height(characters_xbr: bytes, body: str) -> float:
    """``body``'s bind height (model units): its bones' tallest less lowest."""
    rig = Rig.read(characters_xbr, body)
    return max(p[2] for p in rig.positions) - min(p[2] for p in rig.positions)


@functools.lru_cache(maxsize=64)
def _planted(rig: Rig, motion: Clip) -> float | None:
    n = int(motion.length * STRIDE_HZ)
    feet = [k for k, bone in enumerate(rig.bones) if any(w in bone.name.lower() for w in _FEET)]
    tall = max(p[2] for p in rig.positions) - min(p[2] for p in rig.positions)
    if n < 2 or not feet or tall <= 0.0:
        return None
    at = [origins(rig, motion, i / STRIDE_HZ) for i in range(n + 1)]
    speeds = []
    for k in feet:
        low = min(p[k][2] for p in at)
        stance = [(at[i][k][1] - at[i + 1][k][1]) * STRIDE_HZ for i in range(n) if at[i][k][2] - low <= PLANT_BAND * tall]
        if len(stance) >= 5:
            speeds.append(statistics.median(stance))
    return statistics.mean(speeds) if speeds else None


def stride_cells(characters_xbr: bytes, body: Body, plays: dict[int, str], own: dict[str, float | None],
                 his: dict[str, float | None], recipe=frozenset()) -> dict[str, float]:
    """W7's ``walkAnimSpeed`` and ``runAnimSpeed`` for ``body`` (Step 2.133,
    D342, AZ-610): per slot (:data:`STRIDE_SLOTS`) the :func:`stride` of the
    clip it plays (``plays``: slot -> clip) times garret4's cell (``his``)
    over his own clip's stride, so its feet keep pace with the ground as
    his do (2.00 x his walk's, 1.48 x his run's; Balthazar's 2.5 was his
    own run's stride, so at 7 m/s his run played at 2.88 against garret4's
    1.33); the species' own cell (``own``; none without one) where the
    slot plays a stand-in (no ``walk``/``run`` of its own or baked), no
    foot plants, or the stride per bind height isn't within
    :data:`STRIDE_CADENCE` of garret4's (a floating body).  A slot of
    ``recipe`` (a variant's ``slots``, Step 2.171) takes its clip's
    :func:`planted` speed itself: no factor of garret4's, so its feet
    don't slide (D440)."""
    out = {}
    for prop, slot in zip(_STRIDE, STRIDE_SLOTS):
        kind, clip = BASE_CLIPS[slot], plays.get(slot)
        if slot in recipe and clip:
            speed = planted(characters_xbr, body.name, clip)
            if speed:
                out[prop] = speed
                continue
        clip = clip[len(RATE_DIR):] if clip and clip.casefold().startswith(RATE_DIR) else clip   # W28's copy: its clip
        mine = stride(characters_xbr, body.name, clip) if clip and clip.casefold() in (
            kind, f"{BAKED_DIR}{kind}") else None
        g4 = stride(characters_xbr, PLAYER, kind)
        if mine and g4 and his[prop] and mine[0] > 0.0 and g4[0] > 0.0:
            share = (mine[0] / mine[1]) / (g4[0] / g4[1])
            if STRIDE_CADENCE[0] <= share <= STRIDE_CADENCE[1]:
                out[prop] = mine[0] * his[prop] / g4[0]
                continue
        if own[prop]:
            out[prop] = own[prop]
    return out

ROLL = "roll forward"
JUMP_ATTACK = "jump attack"
_ROW_CLIPS = {"basic1": "attack_1", "basic2": "attack_2", JUMP_ATTACK: "attack_2", "basic3": "attack_3"}
_ROLL_CLIPS = ("run", "walk", "idle", "idle_2", "idle_1")
_FALLBACK_CLIPS = ("ouch_1", "run", "walk", "idle")

RATE_MARGIN = 1e-4
"""How much faster than garret4's a standardized move plays (one part in
10,000): a move ends on the first tick whose clip time reaches its end,
and garret4's roll reaches it exactly on its 21st tick, where float
rounding decides: at the exact ratio 23 of the 101 other species with
clips rolled 22 ticks [verified 2026-10-12: ``PlayerSim.roll`` (L2) on
each one's standardized build]."""


def standard_rate(rate: float, clip: float, garret4_clip: float) -> float:
    """The ``Rate`` that plays a ``clip``-second clip in the time
    ``rate`` plays garret4's ``garret4_clip``-second one (W5, D131), made
    faster by :data:`RATE_MARGIN`."""
    return rate * clip / garret4_clip * (1 + RATE_MARGIN)


def move_window(anims, col: int) -> tuple[float, float]:
    """``attacks_anims`` column ``col``'s move, (Move start, Move end2)
    as fractions of its clip, as ``load_attacks_anims_config`` (0x7E2E0)
    reads them: (value - Anim start) / (Anim end - Anim start), else 0
    and 1."""
    name = anims.col_names()[col]
    cells = {row: anims.find_cell(name, row, col) for row in (
        "Anim start", "Anim end", "Move start", "Move end2")}
    value = {row: c.double_value if c is not None and c.type_code == 1 else None
             for row, c in cells.items()}
    a0, a1 = value["Anim start"], value["Anim end"]

    def frac(row: str, default: float) -> float:
        v = value[row]
        return default if v is None or a0 is None or a1 is None or a1 == a0 else (v - a0) / (a1 - a0)
    return frac("Move start", 0.0), frac("Move end2", 1.0)


def windup(rate: float, clip: float, window: tuple[float, float],
           windows: tuple[DamageWindow, ...] | None) -> float:
    """How long, in seconds, a move takes to open its damage window: the
    move plays a ``clip``-second clip from ``window[0]`` to ``window[1]``
    of it at ``rate`` clip seconds a second; the clip's first damage
    window inside the move opens it (``windows``, :func:`damage_windows`:
    the marker on with a length above 0, as the damage pass 0x43A80 needs
    both; Step 2.104, AZ-524: magmar's ``attack_1`` turns its active part
    on at t 0 and its length only at 1.63 s), 0.0 when none falls inside
    it, or X3 at :data:`X3_OPENS` of the move when ``windows`` is None."""
    start, end = window
    if windows is None:
        return X3_OPENS * (end - start) * clip / rate
    lo, hi = start * clip, end * clip
    return next(((max(w.on, lo) - lo) / rate for w in windows if min(w.off, hi) >= max(w.on, lo)), 0.0)


STAFF_BINDS = ("m_stafftop", "m_staffbottom")
_SHOWN = struct.pack("<3f", 1.0, 1.0, 1.0)
_HIDDEN = struct.pack("<3f", 0.001, 0.001, 0.001)


@dataclass(frozen=True)
class PlayerModel:
    """One ``critters_engine`` species as a player model: its body, its
    status (green, yellow, red or ``refused``) and why."""

    species: str
    body: str | None
    status: str
    note: str


def status(species: str) -> tuple[str, str]:
    """``species``' support status and why (:data:`SUPPORT`, else red
    "untested")."""
    return SUPPORT.get(species, UNTESTED)


def _species(engine) -> dict[str, dict]:
    """``{species: {prop: value}}`` of ``critters_engine``'s ``body``,
    ``scale`` and ``boundRadius`` (``None`` for an empty
    cell; a repeated species name keeps its last column, as
    :meth:`~azurik_mod.xbr.sections.KeyedTableSection.find_cell`)."""
    rows = engine.row_names()
    out: dict[str, dict] = {}
    for c, species in enumerate(engine.col_names()):
        values = {}
        for prop in ("body", "scale", "boundRadius"):
            cell = engine.read_cell(c, rows.index(prop))
            values[prop] = {1: cell.double_value, 2: cell.string_value}.get(cell.type_code)
        out[species] = values
    return out


def _refusal(rows: dict, bodies: frozenset[str], species: str) -> str | None:
    """Why ``species`` can't dress the player, or ``None``: ``rows`` is
    :func:`_species`, ``bodies`` :func:`body_names`."""
    if species not in rows:
        return "no such species in config.xbr's critters_engine"
    body = rows[species]["body"]
    if not body:
        return "it has no body"
    if body.casefold() not in bodies:
        return f"its body {body!r} has no model in characters.xbr"
    return None


def player_models(config_xbr: bytes, characters_xbr: bytes, mode: str = DEFAULT_MODE,
                  size: str = DEFAULT_SIZE, model_scale: float = 1.0) -> list[PlayerModel]:
    """Every ``critters_engine`` species, in table order, as a player
    model, with its status in gameplay ``mode`` at ``size`` drawn
    ``model_scale`` times it (:func:`mode_status`)."""
    rows = _species(XbrDocument.from_bytes(config_xbr).keyed_section("critters_engine"))
    bodies = body_names(characters_xbr)
    out = []
    for species, values in rows.items():
        why = _refusal(rows, bodies, species)
        out.append(PlayerModel(species, values["body"],
                               *((REFUSED, why) if why else mode_status(species, mode, size, model_scale))))
    return out


G4_ROLL = "roll_forward"
"""garret4's roll clip, the roll column's vanilla ``Anim``."""


def bakes(body: Body, missing_anims: str) -> bool:
    """Whether a build bakes garret4's clips onto ``body`` (B, Step 2.87;
    D238): under ``missing_anims`` "garret4" for a body
    :data:`~azurik_mod.assets.retarget.MAPS` lists or one with no clips,
    as timers (Step 2.89)."""
    return missing_anims == "garret4" and (not body.clips or body.name.casefold() in BAKED_BODIES)


def floats(species: str, mode: str, baked: bool) -> bool:
    """Whether a build of ``species`` floats its baked body on its own
    clips (Step 2.134a; D334, the owner: "it is supposed to float, as a
    flying enemy", D335): in Balanced (mode ``own``) a :data:`FLYERS`
    species the bake serves (``baked``: the fire and air elementals and
    the air elemental boss) plays its own clips in X11's
    :data:`~azurik_mod.patches._player_slots.FLOATS` slots, garret4-timed
    (X12), and rolls on its own run (X4), not garret4's baked ones, which
    put it on the floor and kick; its ladder, hoist, step and hang stay
    baked.  Skin only keeps garret4's moves (D327)."""
    return mode == "own" and baked and species in FLYERS


def style_picks(style: Style, columns: list[str], picks: list[str]) -> list[str]:
    """``picks`` with each column ``style`` takes playing its clip there
    under its ``dir`` (the roll and any other column keep theirs); a
    source's own build (``own``, Step 2.161c) takes every column, each the
    clip :func:`substitutes` gives that body."""
    chosen = style.picks if style.own is None else dict(zip(columns, substitutes(columns, style.own, True)))
    return [style.dir + chosen[col] if col in chosen and col != ROLL else pick
            for col, pick in zip(columns, picks)]


LIMB_SAMPLES = 8
"""How many steps :func:`style_windows` follows a kit's limb through its window."""


def style_windows(style: Style, picks: list[str], characters: bytes, body: Body,
                  drawn: float) -> dict[str, tuple[DamageWindow, ...]]:
    """X3's window on each pick of ``style`` a build plays (its ``dir`` +
    a clip of its ``windows``), as the build's X3 table plays it
    (:func:`x3_rows`, X3 anchored at the feet) and W5, W14 and W19 weigh
    it: the style's window, clip seconds, with X3's box its own, at the
    body's size (the clip bake's hip ratio, ``rt.hip``), drawn ``drawn``
    times.  A source rig's own build (:attr:`Style.own`, Step 2.195b, D767,
    the owner: "Balthazar's magic ranged"): the box bounding his own
    damage boxes over it (his attack_1's blast, 0.49-1.26 m ahead of his
    feet; his attack_3's lightning beam, to 6.95 m).  A kit's
    (:attr:`Style.limbs`, Step 2.195, D763): the box bounding the bones
    that play the clip's limbs on ``body`` and every bone under them
    through the window (the clip baked as the build bakes it,
    :data:`LIMB_SAMPLES` steps), grown its pad every way (a fist's or a
    foot's length: the source rig's bind distance x the hip ratio): it
    reaches a fist or a foot past the limb at full extension, at the
    body's size, and at least its pad past W19's contact front
    (:data:`PLAYER_RADIUS` x the drawn scale, at least 1: an enemy walked
    up stops there, so a short swing, the child's uppercut or a big body's
    jab, still meets it).  A clip with no window (Balthazar's drain) takes
    X3's :data:`X3_OPENS` to :data:`X3_CLOSES` of its move, as any clip
    without a box (D421's attack_2), with garret4's attack_1 box ahead of
    the feet.  :class:`ValueError` names a kit clip with a window and no
    limbs, or a limb no bone of ``body`` plays (D35)."""
    chosen = sorted({p for p in picks if p.startswith(style.dir) and p[len(style.dir):] in style.windows})
    if not chosen:
        return {}
    rt = Retarget(characters, body.name, grow=False, lender=style.source)
    if style.own is not None:
        out = {}
        for pick in chosen:
            found = damage_windows(characters, style.source, pick[len(style.dir):], rt.hip * drawn)
            low = tuple(min(w.low[c] for w in found) for c in range(3))
            high = tuple(max(w.high[c] for w in found) for c in range(3))
            out[pick] = (DamageWindow(found[0].marker, *style.windows[pick[len(style.dir):]], low, high,
                                      max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1])),
                                      min(w.near for w in found)),)
        return out
    lent, clips = rt.garret4, None
    names = [b.name for b in lent.bones]
    have = {n.casefold() for n in named_resources(characters).values()}
    out = {}
    for pick in chosen:
        name = pick[len(style.dir):]
        if name not in style.limbs:
            raise ValueError(f"{style.source}'s {name}: a hit window and no limbs (kit.json)")
        limbs, (a, b) = style.limbs[name]
        roots = {names.index(n) for n in limbs}
        bones = [k for k, g in rt.source.items() if g in roots or roots & set(lent.ancestors(g))]
        if not bones:
            raise ValueError(f"{body.name}: no bone plays {', '.join(limbs)} of {style.source}'s {name}")
        pad = math.dist(lent.positions[names.index(a)], lent.positions[names.index(b)]) * rt.hip
        if f"characters/{body.name}/{pick}".casefold() in have:   # the build's bake
            clip = named_clip(characters, body.name, pick)
        else:   # the listing's: the same limbs (a bake's post moves only its props)
            clips = clips or style.clips(characters)
            clip = bake_clip(rt, clips[name], drawn)
        on, off = style.windows[name]
        boxes = []
        for n in range(LIMB_SAMPLES + 1):
            at = origins(rt.target, clip, on + (off - on) * n / LIMB_SAMPLES)
            boxes.append(tuple(tuple(drawn * (f(at[k][c] for k in bones) + s * pad) for c in range(3))
                               for f, s in ((min, -1), (max, 1))))
        lo = tuple(min(box[0][c] for box in boxes) for c in range(3))
        hi = tuple(max(box[1][c] for box in boxes) for c in range(3))
        hi = (hi[0], max(hi[1], PLAYER_RADIUS * max(drawn, 1.0) + drawn * pad), hi[2])   # past W19's contact front
        out[pick] = (DamageWindow(DAMAGE_MARKERS[0], on, off, lo, hi,
                                  max(math.hypot(x, y) for x in (lo[0], hi[0]) for y in (lo[1], hi[1])),
                                  min(near(*box) for box in boxes)),)
    return out


def x3_rows(anims, picks: list[str], body: Body, windows: dict[str, tuple[DamageWindow, ...]],
            offset: tuple[float, float, float]) -> list[tuple[float, ...]]:
    """X3's box table (:data:`~azurik_mod.patches._player_damage_marker.BOX`
    rows) for a build with a style's windows (:func:`style_windows`, X3's
    anchor the feet): a style clip's own box over its window, where it
    stands in the model (Step 2.195: the kit's; Step 2.195b: Balthazar's),
    any other column's ``offset`` from the anchor with garret4's attack_1
    extents over X3's :data:`X3_OPENS` to :data:`X3_CLOSES` of its move
    (the shim's own window, as fractions of the clip)."""
    rows = []
    for i, pick in enumerate(picks):
        if pick in windows:
            length = body.length(pick)
            w = windows[pick][0]
            rows.append((w.on / length, w.off / length, *((a + b) / 2 for a, b in zip(w.low, w.high)),
                         *(b - a for a, b in zip(w.low, w.high))))
            continue
        start, end = move_window(anims, i)
        rows.append((start + X3_OPENS * (end - start), start + X3_CLOSES * (end - start), *offset, *GARRET4_EXTENT))
    return rows


@dataclass(frozen=True)
class TipPlan:
    """X3 at a rigid prop's tip (Step 2.161e, :func:`tip_plan`)."""

    bone: int
    """The tip carrier's index, X3's anchor."""
    columns: int
    """Every attack column but the roll: the tip's box replaces the body's own (S3)."""
    rows: list[tuple[float, ...]]
    """X3's box table: each column's window, the box centred on the tip, a cube :data:`TIP_BOX` x k x drawn."""
    forward: float | None
    """The farthest the tip's box reaches straight ahead in the idle swings (m, the logic's reach: :data:`IDLE_SWINGS`, AZ-566), x
    X13's reach and :data:`REACH_BUMP` in a bump column; ``None`` with no column measured."""
    corner: float
    """Its farthest corner from the feet (m, unscaled by X13: X21's search, which scales it)."""
    kept: tuple[str, ...]
    """The columns whose reach stays the body's own: a clip keying a scale over the tip (``origins`` leaves scale
    out, so the tip isn't where it would measure it)."""


def tip_plan(characters: bytes, body: Body, lo: Loadout, anims, columns: list[str], picks: list[str],
             drawn: float, rotate: tuple[list[int], int] | None = None, reach: float = 1.0, bump: int = 0
             ) -> TipPlan:
    """X3's box at ``lo``'s rigid prop's tip (Step 2.161e; the 2.161
    design's 2.6, S3, S4: :attr:`Loadout.tip`) on ``body`` (its carriers
    added as the build adds them last, W31) drawn ``drawn`` times: X3 in
    exact mode with the tip carrier as its bone (main's lent path: no new
    shim), on every attack column in the window of the clip it plays, the
    body's own (its damage windows' first start to last end, as fractions
    of the clip; a column X10 turns, the union of its ring's), else X3's
    :data:`X3_OPENS` to :data:`X3_CLOSES` of its move, its box a cube
    :data:`TIP_BOX` x k x the drawn scale centred on the tip; and the reach
    it measures: the tip sampled through each window
    (:data:`~azurik_mod.patches._player_weapons.HELD_SAMPLES` steps,
    ``origins`` on the body's own clip at the drawn scale) plus
    the box's half side, straight ahead and to its farthest corner, the
    tip's alone (the tip's box replaces the body's own boxes), a column
    whose clip keys a scale over the tip left to the body's own reach
    (:attr:`TipPlan.kept`)."""
    from azurkit.tools.characters._player_weapons import HELD_SAMPLES, add_carriers

    # W31 as the build appends it, last, and W41's keys in its own clips (Step 2.207b), which the box follows
    carried_on = faded_lifted(own_lifted(add_carriers(characters, body, lo), body.name, lo, characters)[0],
                              body.name, lo, characters)[0]
    rig = Rig.read(carried_on, body.name)
    tip = [b.name for b in rig.bones].index(lo.prop.carriers[0])
    over = {tip, *rig.ancestors(tip)}
    side = TIP_BOX * lo.k * drawn
    garret4 = read_body(characters, PLAYER)
    ring, turns = rotate or ([], 0)
    rows, mask, ahead, corners, kept = [], 0, [], [], []
    for i, col in enumerate(columns):
        if col == ROLL:
            rows.append(NO_BOX)
            continue
        mask |= 1 << i
        window, gain = None, reach * (REACH_BUMP if bump >> i & 1 else 1.0)
        for pick in ([picks[h] for h in ring] if turns >> i & 1 else [picks[i]]):
            owner, clip = source_clip(body, garret4, pick)
            length, own = owner.length(clip), damage_windows(characters, owner.name, clip)
            if own:
                on, off = min(w.on for w in own) / length, max(w.off for w in own) / length
            else:
                start, end = move_window(anims, i)
                on, off = start + X3_OPENS * (end - start), start + X3_CLOSES * (end - start)
            window = (on, off) if window is None else (min(window[0], on), max(window[1], off))
            motion = named_clip(carried_on, owner.name, clip)
            if any(tr.comp >= 7 and tr.target in over and any(abs(k[1] - 1.0) > 1e-5 for k in tr.keys)
                   for tr in motion.bones):
                kept.append(col)
                continue
            for s in range(HELD_SAMPLES + 1):
                at = [c * drawn for c in origins(rig, motion, (on + (off - on) * s / HELD_SAMPLES) * length)[tip]]
                low, high = [c - side / 2 for c in at], [c + side / 2 for c in at]
                corners.append(max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1])))
                if col in IDLE_SWINGS:   # the logic's reach (AZ-566)
                    ahead.append(gain * forward(low, high))
        rows.append((*window, 0.0, 0.0, 0.0, side, side, side))
    return TipPlan(tip, mask, rows, max(ahead) if ahead else None, max(corners, default=0.0),
                   tuple(dict.fromkeys(kept)))


def source_clip(body: Body, garret4: Body, pick: str) -> tuple[Body, str]:
    """The body and clip a pick (an ``attacks_anims`` ``Anim`` W3 writes)
    plays, for its length, damage windows and root motion: a baked one
    (B: ``g4/`` + a garret4 clip, ``characters/<body>/g4/<clip>``) is
    garret4's clip, which it plays in his length on his root motion;
    any other the body's own.  Every lookup of a pick on its body goes
    through it (W5, :func:`weigh_attacks`, :func:`reach_misses` and
    :func:`hitting_ring`, :func:`melee_reach`,
    :func:`attacks`, X4's test) but X3's damage-clip test, which reads
    the pick itself: a baked pick is none of the body's damage clips, so
    X3 serves it (:func:`x3_columns`)."""
    return (garret4, pick[len(BAKED_DIR):]) if pick.startswith(BAKED_DIR) else (body, pick)


def substitutes(columns: list[str], body: Body, baked: bool = False,
                exact: list[AnimString] | None = None, *, floats: bool = False,
                borrow: bool = False) -> list[str]:
    """The clip each ``attacks_anims`` column plays on ``body``:

    - the roll: garret4's ``roll_forward`` baked onto the body's rig
      (``g4/roll_forward``) when the build bakes (``baked``,
      :func:`bakes`) and the body doesn't float on its own clips
      (``floats``, :func:`floats`), else the first of run, walk, idle,
      idle_2, idle_1 the body has (X4 moving it as garret4's roll);
    - the jump attack: attack_1 when attack_2 switches no damage marker
      on and attack_1 does (Step 2.24f: balthazar's 2.27 s attack_2 and
      attack_3 took 45 ticks at its Rate against garret4's 11);
    - basic1, basic2, jump attack and basic3: attack_1, attack_2,
      attack_2 and attack_3 when the body has it (the combo plays the
      body's first three attacks: Step 2.64);
    - every other attack: the body's :func:`attack_clips` in turn (a clip
      without a damage window hits through X3; AZ-294 kept those off
      every column before Step 2.64);
    - with none: the first of ouch_1, run, walk, idle;

    and else the body's first clip by name.  In garret4's exact on a body
    the build bakes (``exact``, the table's :func:`anim_strings`) each
    attack column, in table order, plays garret4's own clip for it baked
    onto the rig (``g4/`` + the column's vanilla ``Anim``) when W3 can
    still hold every name (:func:`place_anims`): seven or eight do
    (basic1-3, finish, finish2, finish3, sweep2 and, where the body's own
    clips leave a string, sweep ledge), each in a string no pick plays;
    the others keep the body's own, since no string is left for them
    (and none holds the 19-21 character names) without string-pool
    growth.  X3 gives every column garret4's box and window either way.
    With ``borrow`` (the :class:`Loadout`'s; ``exact`` the table's strings) every
    attack column plays garret4's own clip for it baked onto the rig,
    ``g4/`` + its vanilla ``Anim``, and the roll ``g4/roll_forward``."""
    clips, damage, pool = set(body.clips), body.damage_clips, attack_clips(body)
    out, turn = [], 0
    for col in columns:
        if col == ROLL:
            pick = (BAKED_DIR + G4_ROLL if baked and not floats and G4_ROLL not in clips
                    else next((c for c in _ROLL_CLIPS if c in clips), body.clips[0]))
        elif col == JUMP_ATTACK and "attack_2" not in damage and "attack_1" in damage:
            pick = "attack_1"
        elif _ROW_CLIPS.get(col) in clips:
            pick = _ROW_CLIPS[col]
        elif pool:
            pick, turn = pool[turn % len(pool)], turn + 1
        else:
            pick = next((c for c in _FALLBACK_CLIPS if c in clips), body.clips[0])
        out.append(pick)
    if borrow:
        return [out[i] if col == ROLL else BAKED_DIR + exact[i].value for i, col in enumerate(columns)]
    for i, col in enumerate(columns if exact is not None else ()):
        trial = [*out[:i], BAKED_DIR + exact[i].value, *out[i + 1:]]
        if col != ROLL and place_anims(columns, exact, list(trial), check=True):
            out = trial
    return out


@dataclass(frozen=True)
class AnimString:
    """An ``attacks_anims`` column's ``Anim`` string as W3 finds it: its
    ``value`` (garret4's clip for the column), its ``length`` (a name
    W3 writes there may be no longer) and whether another reference
    ``shared`` it (:func:`~azurik_mod.xbr.edits.set_keyed_string`
    refuses to rewrite one: hose_attack_3's, also its column's name)."""

    value: str
    length: int
    shared: bool


def anim_strings(anims) -> list[AnimString]:
    """Each column's :class:`AnimString` in the ``attacks_anims`` section
    ``anims``, in table order."""
    cells = [anims.find_cell(col, "Anim", i) for i, col in enumerate(anims.col_names())]
    return [AnimString(cell.string_value, cell.string_length, bool(shared))
            for cell, shared in zip(cells, string_sharer_counts(anims, cells))]


def place_anims(columns: list[str], strings: list[AnimString], picks: list[str],
                check: bool = False) -> tuple[dict[int, str], list[tuple[int, int]]] | bool:
    """W3's plan to make each ``attacks_anims`` column (``strings``,
    :func:`anim_strings`) play its pick (:func:`substitutes`): the strings
    it rewrites (column -> name) and the columns it points at another
    column's string, ``(column, holder)``.

    A name no string holds yet goes into the string of the first column
    that plays it, if that string is its own (not shared) and long
    enough; an attack clip of the body no column could hold takes the
    string of a column whose own clip another column plays too (Step 2.64:
    spideyzar's whirlwind fell only on hose_attack_3, whose string is
    shared), and that column plays it (``picks`` is updated); a name in a
    directory (B's ``g4/`` names, each longer than its column's string;
    W17's ``p/`` copies, Step 2.75e) takes a string no pick plays, the
    longest name first, each the shortest that holds it (Step 2.87).
    Every other column points at the string its name's holder held after
    the writes, though the holder moves on (Step 2.73a:
    pointed through the holder's cell after it moved, balthazar's right1,
    left2 and up1 read its attack_1 for their attack_2; Step 2.87: a
    column lending a ``g4/`` name its string may read its own clip
    through the column that name's string serves).  :class:`ValueError`
    names each name no string can hold; with ``check``, whether every
    name has one instead."""
    holder: dict[str, int] = {}
    for i, s in enumerate(strings):
        holder.setdefault(s.value, i)
    writes: dict[int, str] = {}
    for i, pick in enumerate(picks):
        if pick not in holder and "/" not in pick and len(pick) <= strings[i].length and not strings[i].shared:
            writes[i], holder[pick] = pick, i
    roll = columns.index(ROLL)
    for clip in sorted(c for c in set(picks) - set(holder) - {picks[roll]} if "/" not in c):
        held = {holder[p] for p in picks if p in holder}
        for i, pick in enumerate(picks):
            if not (i == roll or i in held or picks.count(pick) < 2
                    or len(clip) > strings[i].length or strings[i].shared):
                picks[i] = writes[i] = clip
                holder[clip] = i
                break
    for clip in sorted(set(picks) - set(holder), key=lambda c: (-len(c), c)):
        free = [i for i, s in enumerate(strings)
                if i not in writes and s.value not in picks and not s.shared and len(clip) <= s.length]
        if free:
            i = min(free, key=lambda i: strings[i].length)
            writes[i], holder[clip] = clip, i
    homeless = sorted(set(picks) - set(holder))
    if check:
        return not homeless
    if homeless:
        raise ValueError(f"attacks_anims has no string to hold {', '.join(homeless)}")
    return writes, [(i, holder[pick]) for i, pick in enumerate(picks)
                    if writes.get(i) != pick and strings[i].value != pick]


def write_anims(anims, plan: tuple[dict[int, str], list[tuple[int, int]]]) -> None:
    """W3 on the ``attacks_anims`` section ``anims``: :func:`place_anims`'
    ``plan`` written, each string it rewrites first, then each other
    column pointed at the string its holder held after them."""
    writes, points = plan
    columns = anims.col_names()
    for i, clip in writes.items():
        set_keyed_string(anims, columns[i], "Anim", clip, col=i)
    held = {h: anims.find_cell(columns[h], "Anim", h) for _, h in points}   # before any moves
    for i, h in points:
        point_keyed_string(anims, columns[i], "Anim", columns[h], "Anim", col=i, src_col=h, src_cell=held[h])


def x3_columns(columns: list[str], picks: list[str], body: Body) -> int:
    """The ``attacks_anims`` columns whose clip on ``body`` (``picks``,
    :func:`substitutes`) switches no damage marker on, as X3's 24-bit
    mask (bit n: column n): every column of a body whose clips switch
    none on, and a baked pick's (B: the bake keeps garret4's damage
    marker tracks only on a body with ``m_damage``, so his box is X3's to
    give)."""
    return sum(1 << i for i, pick in enumerate(picks) if pick not in body.damage_clips)


def needs_damage_marker(columns: list[str], picks: list[str], body: Body) -> bool:
    """Whether some attack (not the roll) plays a clip on ``body`` that
    switches no damage marker on, so X3 must give it one."""
    return any(col != ROLL and pick not in body.damage_clips for col, pick in zip(columns, picks))


def x3_mask(mode: str, columns: list[str], picks: list[str], body: Body, missed: int = 0) -> int:
    """X3's columns for a build on ``body`` in gameplay ``mode`` (``picks``,
    :func:`substitutes`; 0: no X3): garret4's exact, every column
    (garret4's box on each, Step 2.24f); else, when some attack plays a
    clip that switches no damage marker on, those columns
    (:func:`x3_columns`, Step 2.64), and in own body also the columns of
    ``missed``, whose own box fails the reach test
    (:func:`reach_misses`, Step 2.69)."""
    if not picks:
        return 0
    if mode == "garret4":
        return (1 << len(columns)) - 1
    own = x3_columns(columns, picks, body) if needs_damage_marker(columns, picks, body) else 0
    return own | (missed if mode == "own" else 0)


def can_hit(windows: tuple[DamageWindow, ...], near: float | None = None) -> bool:
    """Whether a clip with ``windows`` can hit a ground-level target in
    front of the player (Step 2.69): some box of it reaches
    :data:`HIT_REACH` from the feet, X13's fill bringing every box ahead
    back to the feet, the facing line and the floor (Step 2.132, AZ-605:
    no box of it need come near the feet or down to the ground), and with
    ``near`` its far face comes that far (m) ahead of them, a pressed
    target's near face (AZ-613: X13's fill keeps a box's far faces)."""
    return any(w.reach >= HIT_REACH for w in windows) and (near is None or max(w.high[1] for w in windows) >= near)


def _hitter(characters_xbr: bytes, body: Body, scale: float):
    """``hits(clip)``: whether ``body``'s own box in ``clip`` at ``scale``
    can hit a ground-level target (:func:`can_hit`; a clip with no damage
    window has X3's box, so it can; a :data:`NO_CONTACT` body's never
    can), each clip's windows read once; a clip garret4 doesn't own also
    meets W19's pressed target, :data:`PLAYER_RADIUS` x max(``scale``, 1)
    ahead (Step 2.175a, AZ-613: his own left1, back1 and back2 swing to
    the side and behind by design)."""
    seen: dict[str, tuple[DamageWindow, ...]] = {}
    garret4 = read_body(characters_xbr, PLAYER)

    def windows(clip: str) -> tuple[DamageWindow, ...]:
        if clip not in seen:
            owner, own = source_clip(body, garret4, clip)
            seen[clip] = damage_windows(characters_xbr, owner.name, own, scale)
        return seen[clip]

    def hits(clip: str) -> bool:
        near = None if source_clip(body, garret4, clip)[0].name == PLAYER else PLAYER_RADIUS * max(scale, 1.0)
        return not windows(clip) or (body.name not in NO_CONTACT and can_hit(windows(clip), near))
    return hits


def hitting_ring(characters_xbr: bytes, body: Body, picks: list[str], scale: float,
                 rotate: tuple[list[int], int]) -> tuple[list[int], int]:
    """Own mode's X10 ring (Step 2.69): only the clips of ``rotate``'s
    ring (:func:`rotation`) whose own box on ``body`` at ``scale`` can hit
    a ground-level target as the build plays them, so every rotating
    swing can (:func:`can_hit`; with X13's fill, Step 2.132, spideyzar's
    ten all rotate).  A ring none of whose clips can hit stays whole, and
    X3 serves its columns (:func:`reach_misses`).  The columns that
    rotate stay."""
    hits = _hitter(characters_xbr, body, scale)
    ring, turns = rotate
    keep = [i for i in ring if hits(picks[i])]
    return (keep, turns) if keep else rotate


def reach_misses(characters_xbr: bytes, body: Body, columns: list[str], picks: list[str],
                 scale: float, rotate: tuple[list[int], int] | None = None) -> int:
    """Own mode's reach test (Step 2.69, replacing Step 2.65's interim
    list of p8's four): the attack columns (a mask, the roll never) whose
    own box on ``body`` at ``scale`` can't hit a ground-level target
    (:func:`can_hit`; every attack of a :data:`NO_CONTACT` body), so X3
    serves them: a column X10 turns (``rotate``, :func:`hitting_ring`)
    when some clip its ring can play can't, any other when the clip it
    plays (``picks``) has damage windows and none can (a clip without one
    has X3 already)."""
    hits = _hitter(characters_xbr, body, scale)
    ring, turns = rotate or ([], 0)
    ring_hits = all(hits(picks[i]) for i in ring)
    return sum(1 << i for i, (col, pick) in enumerate(zip(columns, picks)) if col != ROLL
               and not (ring_hits if turns >> i & 1 else hits(pick)))


# --- X10: the attacks rotate through the body's attack clips (Step 2.64) ---
COMBO = 3
"""The clips the combo plays (basic1, basic2, basic3): a body with more
attack clips than this rotates them (X10)."""


def rotation(columns: list[str], picks: list[str], body: Body) -> tuple[list[int], int] | None:
    """X10's ring and columns on ``body`` (``picks``, :func:`substitutes`),
    or ``None`` when its attack clips are no more than the combo's
    :data:`COMBO`: the ring is the first column holding each clip of one
    kind (the clips that switch a damage marker on, or on a body whose
    clips switch none on, all its :func:`attack_clips`), in column order,
    and the columns that rotate through them (a 24-bit mask) are the
    attacks playing one of them but the jump attack, whose clip is
    picked for its time (Step 2.24f).  Within one kind a column's X3 bit
    holds whatever clip plays, so rotation and X3 agree."""
    kind = set(body.damage_clips or attack_clips(body))
    first: dict[str, int] = {}
    for i, pick in enumerate(picks):
        if columns[i] != ROLL and pick in kind:
            first.setdefault(pick, i)
    if len(first) <= COMBO:
        return None
    ring = sorted(first.values())
    rotate = sum(1 << i for i, (col, pick) in enumerate(zip(columns, picks))
                 if col not in (ROLL, JUMP_ATTACK) and pick in kind)
    return ring, rotate


# --- X36's attack sets: WHITE cycles them (Step 2.135, D325) ----------------
SET_SLOTS = ("basic1", "basic2", "basic3", "finish")
"""A set's four slots: the combo's basic1 > basic2 > basic3 > finisher
(finish, finish2 and finish3 all play the set's fourth)."""
SET_COMBO = ("basic1", "basic2", "basic3", "finish", "finish2", "finish3")
"""The columns a set remaps (``attacks_anims``' 0-5), set 0 each its own."""
SETS_MAX = 8
"""The most sets X36's tables hold (the farmers' six)."""
SETS_WRAP = 40
"""The most characters a line of X36's set line holds: its names wrap
there (Step 2.153, D441's corner; D115's default: 40 x 0.8 x 16 px is the
title-safe corner's 512 px)."""


def attack_sets(columns: list[str], picks: list[str]) -> list[list[int]]:
    """The attack sets WHITE cycles on a swapped body playing ``picks``
    (the build's final clip per ``attacks_anims`` column, Step 2.135,
    D325): per set the source column of each of :data:`SET_SLOTS`.  Set 0
    is the game's combo as W3 picks it (basic1, basic2, basic3, finish);
    every other distinct pick, by its first column in table order, the roll
    and :data:`SET_COMBO`'s picks left out, goes four to a set onto the
    slots, a short last set walking back through its own picks (a b c b,
    a b a b, a a a a), so each attack the body has plays from some set and
    no swing follows itself round the set's cycle unless it is the set's
    only one (AZ-680: a b c a played a twice at the wrap).  ``[]`` for a
    body with no clips."""
    if not picks:
        return []
    seen = {picks[columns.index(col)] for col in SET_COMBO}
    rest = []
    for i, (col, pick) in enumerate(zip(columns, picks)):
        if col != ROLL and pick not in seen:
            seen.add(pick)
            rest.append(i)
    chunks = [rest[k:k + len(SET_SLOTS)] for k in range(0, len(rest), len(SET_SLOTS))]

    def walk(j: int, n: int) -> int:   # up the set's n picks and back: 0 1 2 1, 0 1 0 1
        k = j % max(1, 2 * n - 2)
        return min(k, 2 * n - 2 - k)
    return [[columns.index(col) for col in SET_SLOTS]] + [
        [chunk[walk(j, len(chunk))] for j in range(len(SET_SLOTS))] for chunk in chunks]


def set_lines(picks: list[str], sets: list[list[int]]) -> list[str]:
    """What X36 shows in the HUD's top-left corner after a WHITE press
    selects each of ``sets`` (:func:`attack_sets`): "Attack set k/n" and,
    below it, the set's clips in slot order with their dirs (``g4/``,
    ``b/``, ``v/``, ``p/``) stripped and repeats dropped, whole names
    wrapped at :data:`SETS_WRAP` characters a line, at most 79 characters
    (X36's 80-byte slot)."""
    out = []
    for k, cols in enumerate(sets):
        rows = [""]
        for name in dict.fromkeys(picks[c].rsplit("/", 1)[-1] for c in cols):
            rows[-1:] = ([f"{rows[-1]} {name}"] if rows[-1] and len(rows[-1]) + 1 + len(name) <= SETS_WRAP
                         else [rows[-1], name] if rows[-1] else [name])
        out.append("\n".join([f"Attack set {k + 1}/{len(sets)}", *rows])[:79])
    return out


def staff_scales(fx_xbr) -> list[int]:
    """The file offset of the scale (attributes 7-9, three f32) of every
    ``fx.xbr`` transform bound to ``m_stafftop`` or ``m_staffbottom``
    (``docs/XBR_FORMAT.md`` § "Level node graph": a ``node`` section's
    records, read by :mod:`azurik_mod.xbr.nodes`)."""
    out = []
    for entry in parse_toc(fx_xbr):
        if entry.tag != "node":
            continue
        for rec in record_offsets(fx_xbr, entry.file_offset):
            if (rec is None or lstr(fx_xbr, rec) != "transform"
                    or bind_name(fx_xbr, rec) not in STAFF_BINDS):
                continue
            attrs, n_attrs = list_at(fx_xbr, rec + 8)
            if n_attrs != 10:
                raise ValueError(f"fx.xbr: a staff transform at 0x{rec:X} has "
                                 f"{n_attrs} attributes, not 10")
            out.append(attrs + 7 * 4)
    return out


# --- W6: the staff's ends follow the body's hands (Step 2.24f) --------------
_HAND = re.compile(r"hand|wrist|(^|_)w$", re.IGNORECASE)
_NOT_HAND = re.compile(r"endnode|fgr|finger|thumb|pinky|index|mid|ring", re.IGNORECASE)
_DAG = frozenset((
    "camera", "critterGenerator", "dag", "effect", "gameSaveControl", "joint", "light", "locator",
    "lod", "pAccelerator", "pBoxSink", "pBurstEmitter", "pComponent", "pEmitter", "pGravity",
    "pNull", "pSink", "pSystem", "pVortex", "platform", "playerLocation", "polyTrail",
    "puppetMaster", "rumble", "soundEffect", "transform", "worldLocator"))
"""The node types whose record +0x18 is the parent's index: those the XBE
registers as ``dag`` or below [verified 2026-10-15:
:class:`azurik_mod.xbr.nodes.Schema` on the vanilla XBE]."""
_TRANSFORMS = frozenset(("transform", "joint", "lod"))
_SCALE_PLUGS = (7, 8, 9)
"""A transform's scaleX-Z attributes (0 lodVisibility, 1-3 translate, 4-6
rotate, 7-9 scale), the plugs a link that drives its scale targets."""
_KEPT = frozenset(("pAccelerator", "pBoxSink", "pBurstEmitter", "pComponent", "pEmitter", "pGravity",
                   "pNull", "pSink", "pSystem", "pVortex", "light", "polyTrail"))
"""What W6 leaves at full scale at a hand: the particle nodes, the lights
and the trails."""


def hand_bones(body: Body, rooms: tuple[int, int]) -> tuple[str, str] | None:
    """The bones the staff's top and bottom end follow on ``body`` (W6),
    or ``None`` when it has no hand: each end takes the first bone, in the
    body's order, that names a hand or wrist (not a finger or an end node)
    on its side of the bind pose (the top the model's right, x > 0; the
    bottom its left) and fits its bind name's string (``rooms``: the
    lengths of ``m_stafftop`` and ``m_staffbottom``); an end with none
    takes the other end's bone."""
    def side(sign: int, room: int) -> str | None:
        return next((n for n, p in body.bones if _HAND.search(n) and not _NOT_HAND.search(n)
                     and p[0] * sign > 0 and len(n) <= room), None)
    top, bottom = side(1, rooms[0]), side(-1, rooms[1])
    if top is None and bottom is None:
        return None
    return top or bottom, bottom or top


def _staff_graphs(fx_xbr) -> list[tuple[list[int | None], dict[str, int]]]:
    """Each ``fx.xbr`` graph that binds the staff: its records and
    ``{bind name: record}`` of its two staff transforms."""
    out = []
    for entry in parse_toc(fx_xbr):
        if entry.tag != "node":
            continue
        recs = record_offsets(fx_xbr, entry.file_offset)
        ends = {bind_name(fx_xbr, rec): rec for rec in recs
                if rec is not None and lstr(fx_xbr, rec) == "transform"
                and bind_name(fx_xbr, rec) in STAFF_BINDS}
        if ends:
            if set(ends) != set(STAFF_BINDS):
                raise ValueError(f"fx.xbr: a staff graph at 0x{entry.file_offset:X} binds "
                                 f"{sorted(ends)}, not both ends")
            out.append((recs, ends))
    return out


def staff_meshes(fx_xbr, recs: list[int | None], end: int) -> list[int]:
    """The transforms under the staff end ``end`` (a record offset) whose
    scale W6 shrinks to hide the staff's meshes (``platform``) but no
    particles, light or trail: the highest ones whose subtree holds a
    mesh and nothing :data:`_KEPT`, and whose scale no link drives (the
    ice blades' scale is animated).  A mesh that shares its transform
    with particles is an effect, not the staff, and stays: only
    ``fx_staff_water3``'s two water balls, each orbiting with its trail's
    emitter."""
    index = {rec: i for i, rec in enumerate(recs) if rec is not None}
    types = [lstr(fx_xbr, rec) if rec is not None else None for rec in recs]
    kids: dict[int, list[int]] = {}
    driven = set()
    for i, rec in enumerate(recs):
        if rec is None:
            continue
        if types[i] in _DAG:
            kids.setdefault(struct.unpack_from("<i", fx_xbr, rec + 0x18)[0], []).append(i)
        links, n = list_at(fx_xbr, rec + 0x10)
        for k in range(n):
            plug, dst = struct.unpack_from("<HxxI", fx_xbr, links + 24 * k + 0x10)
            if dst < len(types) and types[dst] in _TRANSFORMS and plug in _SCALE_PLUGS:
                driven.add(dst)

    def subtree(i: int) -> set[str]:
        out = {types[i]}
        for c in kids.get(i, ()):
            out |= subtree(c)
        return out

    def hide(i: int) -> list[int]:
        held = subtree(i)
        if "platform" not in held:
            return []
        if types[i] in _TRANSFORMS and not held & _KEPT and i not in driven:
            return [recs[i]]
        return [rec for c in kids.get(i, ()) for rec in hide(c)]

    return [rec for c in kids.get(index[end], ()) for rec in hide(c)]


def follow_hands(fx, hands: tuple[str, str], shape, euler, shrink: bool = True) -> int:
    """W6 on the staged ``fx.xbr`` document ``fx``: bind each staff end of
    every staff graph to its bone of ``hands`` (:func:`hand_bones`) in
    place of garret4's ``m_stafftop`` / ``m_staffbottom``, its power head
    first reshaped for the hand or the hoe (``shape``, Step 2.182, D707:
    :mod:`~azurik_mod.patches._player_power_fx`, ``euler`` the XBE's
    tables), and with ``shrink`` the staff's blades under each end shrunk
    to 0.001 (:func:`staff_meshes` among
    :func:`~azurik_mod.patches._player_power_fx.blades`), so the staff
    stays hidden while its element meshes, particles and trails come from
    the hands (without, Step 2.161g, D618: garret4's hoe, his powers' heads
    whole, only the plain staff's head shrunk, Step 2.206b, AZ-782:
    :func:`~azurik_mod.patches._player_power_fx.plain`).
    An end whose bone's name doesn't fit its own string points its bind at
    the other end's.  Returns the meshes shrunk."""
    from azurkit.tools.characters import _player_power_fx as power

    hidden = power.blades(fx.raw) if shrink else power.plain(fx.raw)
    power.reshape(fx, shape, euler, bound=True)
    shrunk = 0
    for recs, ends in _staff_graphs(fx.raw):
        names = dict(zip(STAFF_BINDS, hands))
        written: dict[str, int] = {}
        for bind in sorted(STAFF_BINDS, key=lambda b: len(names[b]) > len(b)):
            rec = ends[bind]
            length, ref = struct.unpack_from("<Ii", fx.raw, rec + 0x20)
            name = names[bind]
            if len(name) <= length:
                at = rec + 0x24 + ref
                replace_bytes_at(fx, at, name.encode("ascii").ljust(length + 1, b"\0"),
                                 expected=bind.encode("ascii") + b"\0")
                replace_bytes_at(fx, rec + 0x20, struct.pack("<I", len(name)),
                                 expected=struct.pack("<I", length))
                written[name] = at
            else:   # the other end's string holds it (hand_bones: it fits there)
                at = written[name]
                replace_bytes_at(fx, rec + 0x20, struct.pack("<Ii", len(name), at - (rec + 0x24)),
                                 expected=struct.pack("<Ii", length, ref))
        for end in ends.values():
            shrunk += _shrink(fx, recs, end, hidden)
    return shrunk


def _shrink(fx, recs: list[int | None], end: int, hidden: set[int]) -> int:
    """W6's shrink under the staff end ``end``: each of its
    :func:`staff_meshes` in ``hidden`` x 0.001.  Returns how many."""
    shrunk = 0
    for rec in staff_meshes(fx.raw, recs, end):
        attrs, _ = list_at(fx.raw, rec + 8)
        old = bytes(fx.raw[attrs + 7 * 4:attrs + 10 * 4])
        if rec in hidden and any(struct.unpack("<3f", old)):
            replace_bytes_at(fx, attrs + 7 * 4, struct.pack(
                "<3f", *(v * 0.001 for v in struct.unpack("<3f", old))), expected=old)
            shrunk += 1
    return shrunk


# --- W16: the body's own field doesn't hurt the player (Step 2.75d, AZ-450) --
DAMAGE_PLUG = 17
"""A ``platform``'s ``damage`` attribute: its damage level, 0 for none
(0x6AD20 reads it into the platform's collision object)."""


def _default_fx(characters: bytes, body: str) -> tuple[list[int | None], list[tuple[int, int, int]]]:
    """``body``'s default fx (``characters/<body>/fx/fx_default``, which
    0x43700 builds on every critter of that body; the player's clone where
    the build adds one, :func:`player_fx_key`): its
    records' offsets and its links, each (source record, target plug,
    target record); none when the body has no default fx."""
    index = {n.casefold(): i for i, n in named_resources(characters).items()}
    at = index.get(player_fx_key(characters, body))
    if at is None:
        return [], []
    recs = record_offsets(characters, parse_toc(characters)[at].file_offset)
    links = []
    for src, rec in enumerate(recs):
        if rec is not None:
            start, n = list_at(characters, rec + 0x10)
            links += [(src, *struct.unpack_from("<HxxI", characters, start + 24 * k + 0x10)) for k in range(n)]
    return recs, links


def field_damage(characters: bytes, body: str, config_xbr: bytes) -> set[str]:
    """The damage types the live damage platforms of ``body``'s default
    fx (:func:`_default_fx`) deal: each ``platform`` whose ``damage``
    level no link drives, as the ``damage`` table's type whose ``Type``
    is the platform's fourcc (+0x44) at that ``Level`` (tesla_tree's
    ``Damage_Field``: ``tela`` 1, ``tesla``).  balthazar_airship's box is
    driven by ``m_lifedrainswitch``, so it isn't live (W17's)."""
    from azurkit.tools.characters.ports import load_all_tables

    recs, links = _default_fx(characters, body)
    if not recs:
        return set()
    driven = {(plug, dst) for _, plug, dst in links}
    table = load_all_tables(config_xbr, sections=("damage",))["damage"]
    kinds = set()
    for i, rec in enumerate(recs):
        if rec is None or lstr(characters, rec) != "platform" or (DAMAGE_PLUG, i) in driven:
            continue
        attrs, _ = list_at(characters, rec + 8)
        level = struct.unpack_from("<f", characters, attrs + 4 * DAMAGE_PLUG)[0]
        fourcc = bytes(characters[rec + 0x44:rec + 0x48]).rstrip(b"\0").decode("latin-1")
        kinds |= {c for c in table.col_names if level and table.get_value(c, "Type")[1] == fourcc
                  and table.get_value(c, "Level")[1] == level}
    return kinds


# --- W17: the body's own switched field doesn't hurt the player (Step 2.75e, AZ-453)
SELF_DIR = "p/"
"""Where W17 stores a copy of a body's clip for the player alone:
``characters/<body>/p/<n>``, the n-th of :func:`self_drains` by name
(short, so any free ``attacks_anims`` string holds it)."""
SIZED_ROLL = SELF_DIR + "roll"
"""garret4's own body drawn at a size other than 1: the clip his roll
column plays, his ``roll_forward`` drawn about his centre at that size
(:func:`~azurik_mod.assets.retarget.centred`, Step 2.133, AZ-608),
``characters/garret4/p/roll`` (short enough for the roll's own string,
which ``g4/roll_forward`` isn't)."""


def field_switches(characters: bytes, body: str) -> set[str]:
    """The markers that switch on a damage platform of ``body``'s default
    fx (:func:`_default_fx`): the bind name of each ``transform`` with a
    link that drives a ``platform``'s ``damage`` level (balthazar_airship's
    and balthazar_spider's ``m_lifedrainswitch``, whose ``damageBox``
    hangs under ``onPlayer``, inherit mode 7: on the player critter,
    ``docs/RE_XBE.md``)."""
    recs, links = _default_fx(characters, body)

    def kind(i: int) -> str | None:
        return lstr(characters, recs[i]) if i < len(recs) and recs[i] is not None else None

    return {name for src, plug, dst in links
            if plug == DAMAGE_PLUG and kind(dst) == "platform" and kind(src) == "transform"
            and (name := bind_name(characters, recs[src]))}


def self_drains(characters: bytes, body: Body) -> dict[str, Clip]:
    """Each clip of ``body`` that keys one of its :func:`field_switches`
    above 0, so switches on a damage field of its own default fx, which
    the player wearing the body wears too and the game lets hurt its
    wearer (no platform hit is checked against its owner,
    ``docs/RE_XBE.md``): balthazar_airship's ``attack_2``, ``damageBox``
    on the player for 1 s of its 2.27 s, ``norm_2`` (15 HP).  Each as
    W17's copy: the clip without its tracks on those markers."""
    switches = field_switches(characters, body.name)
    marks = {i for i, name in enumerate(body.markers) if name in switches}
    if not marks:
        return {}
    toc = parse_toc(characters)
    by_name = {n.casefold(): i for i, n in named_resources(characters).items()}
    out = {}
    for clip in body.clips:
        whole = read_clip(characters, toc[by_name[f"characters/{body.name}/{clip}".casefold()]].file_offset)
        if _keys(whole, marks):
            out[clip] = quiet(whole, marks)
    return out


def _keys(clip: Clip, marks: set[int]) -> bool:
    """Whether ``clip`` keys one of the markers ``marks`` above 0 (switches it on)."""
    return any(track.target in marks and any(key[1] > 0 for key in track.keys) for track in clip.markers)


# --- W22: a worn body's death plays without its scripted fx (Step 2.131, AZ-603, D343)
QUIET_DIR = "q/"
"""Where W22 stores the player's copy of a clip that starts its body's
scripted fx: ``characters/<body>/q/<clip>``, which X11's table alone
names."""
SCRIPTED = frozenset(("camera", "critterGenerator"))
"""The default-fx nodes that script a scene (W22): a game camera (vtable
0x19C2F8, pushed on the level's camera stack, its ``freezePlayer``
holding the player's input) and a critter generator, which spawns
critters (bosses/air_guardian's ``frag_air_4``, the air disc fragment)."""
_RELAYS = frozenset(("switch", "latch"))


def scripted_switches(characters: bytes, body: str) -> set[str]:
    """The markers that start a scripted scene in ``body``'s default fx
    (:func:`_default_fx`): the bind name of each ``transform`` whose links
    reach a :data:`SCRIPTED` node, directly or through ``switch`` and
    ``latch`` nodes.  ``m_dying`` on bosses/air_guardian (its death camera
    and the ``frag_air_4`` generator), bosses/fire_guardian (its
    ``DeathCam_toggle``) and balthazar_airship (its ``deathCam_toggle``),
    and fire_guardian's ``m_shards`` (its ``fire_shard`` generator)."""
    recs, links = _default_fx(characters, body)

    def kind(i: int) -> str | None:
        return lstr(characters, recs[i]) if i < len(recs) and recs[i] is not None else None

    out: dict[int, list[int]] = {}
    for src, _, dst in links:
        out.setdefault(src, []).append(dst)

    def reaches(start: int) -> bool:
        seen, todo = set(), list(out.get(start, ()))
        while todo:
            if (i := todo.pop()) in seen:
                continue
            seen.add(i)
            if kind(i) in SCRIPTED:
                return True
            if kind(i) in _RELAYS:
                todo += out.get(i, ())
        return False

    return {name for src in out if kind(src) == "transform" and reaches(src)
            and (name := bind_name(characters, recs[src]))}


def quiet_fills(characters: bytes, body: Body, table: dict[int, tuple[str, float]],
                skip=()) -> tuple[dict[int, tuple[str, float]], dict[str, Clip]]:
    """W22 (Step 2.131, AZ-603): X11's fills for each asked slot but the
    hits (X7 plays its own there) and ``skip`` (the slots a recipe's
    ``idles`` fill, Step 2.168) whose clip keys one of ``body``'s
    :func:`scripted_switches` above 0, each ``q/<clip>``
    (:data:`QUIET_DIR`) in the slot's length, and those copies (a name
    under the body -> its clip: the clip without its tracks on those
    markers, :func:`~azurik_mod.assets.retarget.quiet`).  A slot's clip
    is the body's own of the slot's name, else ``table``'s (X11's fills)
    when that is one of the body's own clips.  A worn boss's ``die`` then
    plays its motion and explosions without its death camera or drop."""
    switches = scripted_switches(characters, body.name)
    marks = {i for i, name in enumerate(body.markers) if name in switches}
    if not marks:
        return {}, {}
    have = {c.casefold(): c for c in body.clips}
    copies: dict[str, Clip | None] = {}
    fills: dict[int, tuple[str, float]] = {}
    for slot in sorted(ASKED - HIT - set(skip)):
        clip, length = have.get(BASE_CLIPS[slot]), 0.0
        if clip is None and slot in table and "/" not in table[slot][0]:
            clip, length = have.get(table[slot][0].casefold()), table[slot][1]
        if clip is None:
            continue
        name = QUIET_DIR + clip
        if name not in copies:
            whole = named_clip(characters, body.name, clip)
            copies[name] = quiet(whole, marks) if _keys(whole, marks) else None
        if copies[name] is not None:
            fills[slot] = (name, length)
    return fills, {name: clip for name, clip in copies.items() if clip is not None}


CENTRED_DIR = "c/"
"""Where an attack pick's copy drawn about the centre goes when no W17 or
W22 copy serves it: ``characters/<body>/c/<n>`` (:func:`attack_copies`,
Step 2.175, AZ-623)."""


def attack_copies(characters: bytes, body: Body, picks: list[str], mode: str,
                  drawn: float = 1.0, switches: set[str] | None = None) -> dict[str, tuple[str, Clip]]:
    """The copies W3 names for ``body``'s attack ``picks`` (a pick -> its
    copy's name under the body and the copy), which every other step
    reads as the pick (each lasts and hits as it does): W17's,
    each of :func:`self_drains`' clips without its field's switch,
    ``p/<n>`` (:data:`SELF_DIR`, the n-th drain by name; none in own mode,
    where X37 turns the field on its target), and W22's on the attacks
    (Step 2.175, AZ-611), in every mode: each other pick of the body's
    own clips that keys one of its :func:`scripted_switches` above 0,
    ``q/<n>`` (:data:`QUIET_DIR`, the n-th of them by name), every copy
    without those markers' tracks: a worn fire guardian's ``attack_2``,
    12 of guard_fire1's 24 columns, keys ``m_shards``, which drives its
    default fx's ``fire_shard`` generator (maxAlive 5).  At a ``drawn``
    scale other than 1 (Step 2.175, AZ-623) each of those copies and
    each other own pick whose clip moves ``m_feet`` (a lunge,
    :func:`~azurik_mod.assets.characters.moves_root`) is drawn about the
    centre, :func:`~azurik_mod.assets.retarget.centred` as the roll's
    (E), the latter ``c/<n>`` (:data:`CENTRED_DIR`): keylord's own
    ``attack_1`` led its centre (D - 1) x its ``m_feet``, 0.16 m at its
    own D 2, then slid back over the exit.  Its damage markers keep their
    tracks, so its boxes hit where every step reads them (D x the clip's
    from where the attack starts) and X3's box on a hand, which follows
    the drawn hand, stays at or past garret4's box at his for D above 1
    (the hand leads ``m_feet`` at the peak of every lunge's window:
    Step 2.175's read of the hand on its clip copies).
    ``switches`` (default: :func:`scripted_switches` in ``characters``)
    names the W22 markers, so a second call after W34's cast, whose clone
    of his graph the player then plays, names the same copies."""
    switches = scripted_switches(characters, body.name) if switches is None else switches
    marks = {i for i, name in enumerate(body.markers) if name in switches}
    drains = self_drains(characters, body) if mode != "own" else {}
    out = {clip: (f"{SELF_DIR}{k}", quiet(copy, marks)) for k, (clip, copy) in enumerate(sorted(drains.items()))
           if clip in picks}
    own = [(clip, named_clip(characters, body.name, clip)) for clip in sorted(set(picks) - set(out))
           if clip in body.clips] if marks else []
    out |= {clip: (f"{QUIET_DIR}{k}", quiet(whole, marks))
            for k, (clip, whole) in enumerate((c, w) for c, w in own if _keys(w, marks))}
    lunges = sorted(clip for clip in set(picks) if clip in body.clips and drawn != 1.0 and drawn
                    and math.isfinite(drawn) and moves_root(characters, body.name, clip))
    if lunges:
        feet = body.markers.index(ROOT_NODE)
        roots = {k: b.t for k, b in enumerate(Rig.read(characters, body.name).bones) if b.parent < 0}
        boxes = {i for i, m in enumerate(body.markers) if m in DAMAGE_MARKERS}
        fresh = 0
        for clip in lunges:
            name, copy = out.get(clip) or (None, named_clip(characters, body.name, clip))
            try:
                drawn_copy = centred(copy, drawn, feet, roots, boxes)
            except ValueError as exc:
                raise ValueError(f"{body.name}'s {clip} drawn about its centre: {exc}") from None
            if name is None:
                name, fresh = f"{CENTRED_DIR}{fresh}", fresh + 1
            out[clip] = (name, drawn_copy)
    return out


CAST_DIR = "k/"
"""Where W34's cast copies go on a body with no attack clip of its own
(Step 2.204, D810: Balthazar's magic on a flicken, a gem or a fish):
``characters/<body>/k/<n>``, a copy of each clip its attack columns play
(:func:`cast_picks`), which W3 names and
:func:`~azurik_mod.patches._player_weapons.cast_copies` keys, so the
clip its other slots play stays its own."""


def cast_picks(columns: list[str], picks: list[str]) -> set[str]:
    """The clips the attack ``columns`` play (W3's ``picks``), the roll's left out: where a body with no attack
    clip casts (Step 2.204)."""
    return {pick for col, pick in zip(columns, picks) if col != ROLL}


def with_casts(characters: bytes, body: Body, columns: list[str], picks: list[str],
               copied: dict[str, tuple[str, Clip]]) -> dict[str, tuple[str, Clip]]:
    """W3's ``copied`` (:func:`attack_copies`) and a :data:`CAST_DIR` copy
    of each clip of ``body``'s own its attack columns play that has none
    (Step 2.204, D810), numbered in name order."""
    wanted = sorted(clip for clip in cast_picks(columns, picks) - set(copied) if clip in body.clips)
    return copied | {clip: (f"{CAST_DIR}{k}", named_clip(characters, body.name, clip)) for k, clip in enumerate(wanted)}


SWIM_HOLD_DIR = "h/"
"""Where W25's held swim copy goes under its body: ``characters/<body>/h/<clip>``."""
SWIM_HOLDS = frozenset({"bosses/air_guardian"})
"""The bodies whose swim W25 holds (guard_air's and guard_air_clone's)."""
SWIM_SLOT = 0x4A
"""X11's swim slot (``swim_2``)."""
SWIM_HOLD_LENGTH = 600.0
"""W25's copy's length (s): long past any swim, its tracks holding their
last keys (modes 0) after the clip's own end."""
SWIM_BOB = (0.25, 2.4)
"""W25's bob (D419, the owner: "Slow bob"): after the clip's own end the
barrel rises and falls this many model units (5% of guard_air's 5.54)
over this many seconds, its root's and every marker's height keyed flat
at each half period to the copy's end, so each half is a smoothstep (the
agents' pick: its ``run``'s own bob is 0.039 units, nearly still)."""


def _less(keys, minus, base: float) -> tuple[tuple[float, float, float, float], ...]:
    """The curve ``keys`` less (``minus`` - ``base``), exact: split at the
    union of both curves' key times, each key the difference's value and
    its slope on either side."""
    rows = []
    for t in sorted({k[0] for k in keys} | {k[0] for k in minus}):
        (vi, vo), (mi, mo) = _slopes(keys, t), _slopes(minus, t)
        rows.append((t, evaluate(keys, t) - evaluate(minus, t) + base, vi - mi, vo - mo))
    return tuple(rows)


def _bobbed(keys, end: float) -> tuple[tuple[float, float, float, float], ...]:
    """``keys`` (ending at ``end``) going on to :data:`SWIM_HOLD_LENGTH`
    with :data:`SWIM_BOB`'s bob on their last value: a flat key every
    half period, up then back."""
    rise, period = SWIM_BOB
    base, n = evaluate(keys, end), int((SWIM_HOLD_LENGTH - end) / (period / 2))
    return (*keys, *((end + k * period / 2, base + (rise if k % 2 else 0.0), 0.0, 0.0) for k in range(1, n + 1)))


def held_swim(characters: bytes, body: Body,
              fills: dict[int, tuple[str, float]]) -> tuple[dict[int, tuple[str, float]], dict[str, Clip]]:
    """W25 (Step 2.134a; D341, the owner on guard_air: "it make a
    somersault and straightens into a barrel for swimming, but then
    resets the animation jarringly"; D419: "Slow bob"): on a
    :data:`SWIM_HOLDS` body, X11's
    swim slot (:data:`SWIM_SLOT`; ``fills``' pick, ``run_begin``,
    garret4-timed and looped: its 2.0 s somersault drifts the root 7.35
    model units ahead and each wrap snapped it back upright) plays a copy,
    ``h/<clip>`` untimed, :data:`SWIM_HOLD_LENGTH` s long, so the
    somersault plays once at rate 1 and every track then holds the
    barrel's pose while its root's and markers' height bob
    (:data:`SWIM_BOB`), but ``m_root``'s (Step 2.134b, AZ-634: the swim
    places the model at its centre less ``m_root``, 0x42E40, so a bobbed
    ``m_root`` cancelled the bob); its root's forward (y) track holds its t 0 value, so the
    barrel stays over the player and turns with it rather than 6 units
    ahead, and each marker's y (the tail and root fx points) is moved
    back by the same drift, so its fx ride the body.  A swim started
    while that layer still plays or fades goes on from its time
    (0xCAE20); a new one starts the somersault again.  Returns the fill
    and the copy (a name under the body -> its clip), or nothing."""
    pick = fills.get(SWIM_SLOT, ("", 0.0))[0]
    if body.name.casefold() not in SWIM_HOLDS or not pick or "/" in pick:
        return {}, {}
    clip = named_clip(characters, body.name, pick)
    root = next(k for k, b in enumerate(Rig.read(characters, body.name).bones) if b.parent < 0)
    drift = next((tr for tr in clip.bones if (tr.target, tr.comp) == (root, 1)), None)
    if drift is None:
        return {}, {}
    y0 = evaluate(drift.keys, 0.0)
    bones = tuple(replace(tr, keys=((0.0, y0, 0.0, 0.0), (SWIM_HOLD_LENGTH, y0, 0.0, 0.0))) if tr is drift else
                  replace(tr, keys=_bobbed(tr.keys, clip.length)) if (tr.target, tr.comp) == (root, 2) else tr
                  for tr in clip.bones)
    m_root = body.markers.index("m_root") if "m_root" in body.markers else -1   # the swim's place (AZ-634)
    markers = tuple(replace(tr, keys=_less(tr.keys, drift.keys, y0)) if tr.comp == 1 else
                    replace(tr, keys=_bobbed(tr.keys, clip.length)) if tr.comp == 2 and tr.target != m_root else tr
                    for tr in clip.markers)
    name = SWIM_HOLD_DIR + pick
    return {SWIM_SLOT: (name, 0.0)}, {name: Clip(SWIM_HOLD_LENGTH, bones, markers)}


# --- W27: a baked body swims at the surface as garret4 does (Step 2.134b, AZ-638) ---
SURFACE_DIR = "s/"
"""Where W27's swim copies go under its body: ``characters/<body>/s/<pick>``."""
SURFACE_SLOTS = (0x46, 0x47, 0x48, 0x4A)
"""The swim slots W27 copies: swim_idle, swim_idle_up, swim_idle_down and
swim_2, the ones the player asks for (it never asks swim_1, 0x49)."""
SURFACE_MARKER = "m_root"
"""The marker player_swim_tick places the model by (0x8BD56)."""
SURFACE_EYE = "m_eye"
"""W27's second marker (Step 2.150, AZ-642; on no body, in no XBR file
and not in the XBE): X8's swim top over its eye height (eye.c), resting
at 1 (:func:`surfaced_swim`)."""
SURFACE_FLOOR = 0.6
"""How high over the surface, at least, a W27 body's swim camera rests
(m; Step 2.150): 0x81E10's 0.4 m push band and the 0.2 m clearance Steps
2.107 and 2.116 keep (:func:`swim_margins`), under garret4's own at x1
(1.56-1.83 m), where the size's max(2s, 0.6) held it 2.00 m over."""


def surfaced_swim(characters: bytes, body: Body, fills: dict[int, tuple[str, float]], drawn: float
                  ) -> tuple[dict[int, tuple[str, float]], dict[str, Clip]]:
    """W27 (Step 2.134b, AZ-638; the owner on town_female_4: "our model is
    fully out of the water floating above the water when we are at the
    max elevation in the water", "this also might be causing her camera to
    look like its too far above her in the water"): player_swim_tick
    (0x8B700) places the model each tick at the swim's centre less
    :data:`SURFACE_MARKER` sampled in the playing clip, unscaled (0x42E40
    at 0x8BD79), and a body without the marker samples zeros, so its
    origin is the centre and a baked body's root is drawn ``drawn`` x its
    swim pose's root over it: town_female_4's top 1.33-1.45 m over the
    surface where garret4's is 0.19-0.25 m under, and the camera, which
    follows the drawn top over the water (X8), with it.  On a body the
    bake maps (:data:`BAKED_BODIES`) without the marker whose swim_idle
    slot plays a baked clip, each :data:`SURFACE_SLOTS` slot ``fills``
    gives a baked clip plays a copy, :data:`SURFACE_DIR` + its pick, keyed
    with the marker's translation ``drawn`` x its root bone's (the clip's
    track, values and slopes x ``drawn``: exact, a Hermite curve being
    linear in both; a component the clip doesn't key, its rest, two keys),
    so the swim draws the root at the centre as garret4's.  Each copy also
    keys :data:`SURFACE_EYE` (Step 2.150, AZ-642) with garret4's head
    over his root in his own clip over his eye height, (``m_head`` -
    ``m_root``) / 1.9925 (his ``m_head`` is one height per swim clip, so
    his ``m_root``'s track turned: exact), which X8 (eye.c) puts over the
    drawn root at the body's share of his eye, so its camera sits where
    his sits over his body.  The markers go at the end of the body's
    table, in that order (the caller grows them, garret4's ``m_root``
    record, at rest zeros, and the eye's at (0, 0, 1), so no other clip
    moves either).  Returns the fills and the copies, or nothing.
    :class:`ValueError` when a key at ``drawn`` doesn't fit a float32, or
    garret4's ``m_head`` moves in a swim clip."""
    pick = fills.get(SURFACE_SLOTS[0], ("", 0.0))[0]
    if (body.name.casefold() not in BAKED_BODIES or SURFACE_MARKER in body.markers
            or not pick.startswith(BAKED_DIR)):
        return {}, {}
    rt = Retarget(characters, body.name, grow=False)
    if rt.root is None:
        return {}, {}
    marker, rest = len(body.markers), rt.target.bones[rt.root].t
    his = [m.casefold() for m in read_body(characters, PLAYER).markers]
    records = dict(marker_records(characters, PLAYER))
    head, root, eye = his.index(CAMERA_MARKER), his.index(SURFACE_MARKER), records[CAMERA_MARKER][2]

    def eye_track(clip: str, length: float) -> Track:
        """:data:`SURFACE_EYE`'s z in the copy of garret4's ``clip``."""
        own = named_clip(characters, PLAYER, clip)
        keyed = {tr.target: tr for tr in own.markers if tr.comp == 2 and tr.target in (head, root)}
        keys = keyed[head].keys if head in keyed else ((0.0, eye, 0.0, 0.0),)
        if any(abs(k[1] - keys[0][1]) > 1e-6 or abs(k[2]) > 1e-6 or 1e-6 < abs(k[3]) <= FLT_MAX for k in keys):
            raise ValueError(f"W27: garret4's {CAMERA_MARKER} moves in his {clip}")   # his slopes: 1e-14
        h = keys[0][1]
        if root not in keyed:   # his m_root's rest
            at = (h - records[SURFACE_MARKER][2]) / eye
            return Track(marker + 1, 2, ((0.0, at, 0.0, 0.0), (length, at, 0.0, 0.0)))
        return Track(marker + 1, 2, tuple((t, (h - v) / eye, -i / eye, o if o > FLT_MAX else -o / eye)
                                          for t, v, i, o in keyed[root].keys), keyed[root].modes)

    def scaled(x: float) -> float:
        if not abs(drawn * x) <= FLT_MAX:
            raise ValueError(f"W27: {body.name}'s swim root x {drawn:g} doesn't fit a float32")
        return drawn * x
    out_fills: dict[int, tuple[str, float]] = {}
    copies: dict[str, Clip] = {}
    for slot in SURFACE_SLOTS:
        pick, length = fills.get(slot, ("", 0.0))
        if not pick.startswith(BAKED_DIR):
            continue
        clip = named_clip(characters, body.name, pick)
        keyed = {tr.comp: tr for tr in clip.bones if tr.target == rt.root and tr.comp <= 2}
        tracks = [Track(marker, c, tuple((t, scaled(v), scaled(i), o if o > FLT_MAX else scaled(o))
                                         for t, v, i, o in keyed[c].keys), keyed[c].modes) if c in keyed else
                  Track(marker, c, ((0.0, scaled(rest[c]), 0.0, 0.0), (clip.length, scaled(rest[c]), 0.0, 0.0)))
                  for c in range(3)]
        tracks.append(eye_track(pick[len(BAKED_DIR):], clip.length))
        out_fills[slot] = (SURFACE_DIR + pick, length)
        copies[SURFACE_DIR + pick] = replace(clip, markers=(*clip.markers, *tracks))
    return out_fills, copies


# --- D219: one action point per body (Step 2.64) ---------------------------
CHEST = (0.4, 0.7)
"""The chest point of a body with neither a hand nor a damage marker:
(0, 0.4 m x its height over garret4's, 0.7 x its height), in front of
its chest (its height: its bind pose's top; for a body whose bones lie
flat or at the origin, its mesh's
:func:`~azurik_mod.assets.characters.height` (Step 2.68: the firefly's
0.174, so sized to garret4's height its chest is at 0.7 x his, not
8 m up); 1 for a body with neither)."""


@dataclass(frozen=True)
class ActionPoint:
    """Where a body's attacks hit and its element effects come from
    (D219): ``kind`` ``"hand"`` (its hand bones, W6: ``hands`` the
    staff's top and bottom ends' bones, ``bone`` the top end's index, the
    one X3's box follows), ``"marker"`` (the fixed ``point`` where its
    ``m_damage`` hits: :func:`~azurik_mod.assets.characters.damage_anchor`
    of the clip basic1 plays, else its first damage clip) or ``"chest"``
    (the fixed ``point`` :data:`CHEST`), in model units."""

    kind: str
    hands: tuple[str, str] | None = None
    bone: int = -1
    point: tuple[float, float, float] = (0.0, 0.0, 0.0)


def action_point(characters: bytes, body: Body, picks: list[str]) -> ActionPoint:
    """``body``'s :class:`ActionPoint`: its hands when it has one
    (:func:`hand_bones`), else where its ``m_damage`` hits, else in front
    of its chest.  A damage marker bound by name would put the staff's
    particles at its resting place, the body's origin (0xCAB80 starts
    from its defaults, (0, 0, 0)), and give them its extents as their
    scale (0xCCDF0 copies the marker's +0x20 into the bind's scale), so
    the point is fixed where the marker hits."""
    hands = hand_bones(body, tuple(len(b) for b in STAFF_BINDS))
    if hands:
        return ActionPoint("hand", hands, [n for n, _ in body.bones].index(hands[0]))
    if "m_damage" in body.markers and body.damage_clips:
        clip = picks[0] if picks and picks[0] in body.damage_clips else body.damage_clips[0]
        return ActionPoint("marker", point=damage_anchor(characters, body.name, clip))
    tall = body_height(characters, body)
    garret4 = read_body(characters, PLAYER).top
    return ActionPoint("chest", point=(0.0, CHEST[0] * tall / garret4, CHEST[1] * tall))


X3_HALF = tuple(0.5 * e for e in GARRET4_EXTENT)
"""X3's box's half extents, in garret4's units (its marker's length 0.5
times garret4's attack_1 extents)."""
X3_SAMPLES = 16
"""How many steps :func:`x3_anchor` follows a hand through X3's window."""


def x3_anchor(characters: bytes, body: Body, point: ActionPoint, anims, picks: list[str], x3: int,
              scale: float, rotate: tuple[list[int], int] | None = None, side: float = 1.0
              ) -> tuple[int, tuple[float, float, float], tuple[float, float, float]]:
    """Where X3's box goes outside garret4's exact, as
    :func:`install_damage_marker` takes it (its bone, point and offset):
    at the body's action point ``point`` (D219; garret4's box 1.2341 m
    ahead of a hand or the chest point, on the point where its m_damage
    hits), unless there, in some column of ``x3`` (playing its pick,
    ``picks``, or for a column X10 turns every clip of ``rotate``'s
    ring), it never comes within :data:`HIT_NEAR` of the feet at the
    build's ``scale`` through X3's window (:data:`X3_OPENS` to
    :data:`X3_CLOSES` of the move, :func:`move_window`, a hand followed
    through its clip, :func:`~azurik_mod.assets.retarget.origins`; a baked
    pick swings it as garret4 swings his; a hand's sideways place x
    ``side``, as the shim puts it: :func:`x3_side`): then garret4's box
    where he holds it, on every column (Step 2.70b: guard_earth's hand
    passes 6.5-8.5 m ahead of its feet through X3's window, guard_water's
    attack_1 hand 3.6 m off at its nearest)."""
    offset = (0.0, 0.0, 0.0) if point.kind == "marker" else (0.0, GARRET4_BOX[1], 0.0)
    rig = Rig.read(characters, body.name) if point.kind == "hand" else None
    toc = parse_toc(characters) if rig else []
    keys = {name.casefold(): i for i, name in named_resources(characters).items()} if rig else {}
    ring, turns = rotate or ([], 0)
    columns = anims.col_names()

    def box_near(at: tuple[float, float, float]) -> float:
        centre = [a * scale * (side if rig is not None and i == 0 else 1.0) + o
                  for i, (a, o) in enumerate(zip(at, offset))]
        return near([c - h for c, h in zip(centre, X3_HALF)], [c + h for c, h in zip(centre, X3_HALF)])

    def nearest(clip: str, window: tuple[float, float]) -> float:
        if rig is None or clip.startswith(BAKED_DIR) or f"characters/{body.name}/{clip}".casefold() not in keys:
            return box_near(point.point)   # a baked pick, or a style's before its bake (the listing)
        motion = read_clip(characters, toc[keys[f"characters/{body.name}/{clip}".casefold()]].file_offset)
        start, end = window
        return min(box_near(origins(rig, motion, motion.length * (start + (end - start) * (
            X3_OPENS + (X3_CLOSES - X3_OPENS) * n / X3_SAMPLES)))[point.bone]) for n in range(X3_SAMPLES + 1))
    seen: dict[tuple[str, tuple[float, float]], float] = {}
    for i, col in enumerate(columns):
        if col == ROLL or not x3 >> i & 1:
            continue
        window = move_window(anims, i)
        for clip in [picks[h] for h in ring] if turns >> i & 1 else [picks[i]]:
            if (clip, window) not in seen:
                seen[clip, window] = nearest(clip, window)
            if seen[clip, window] > HIT_NEAR:
                return -1, (0.0, 0.0, 0.0), GARRET4_BOX
    return point.bone, point.point, offset


def body_height(characters: bytes, body: Body) -> float:
    """``body``'s height in model units as its chest point (:data:`CHEST`)
    and W15 measure it: the top of its bind pose, else (no bone 1e-3 over
    the origin: the water tentacles' bones lie flat, top 9.02e-10, which
    sized their armor to nothing, AZ-558) its mesh's
    :func:`~azurik_mod.assets.characters.height`, else 1."""
    return body.top if body.top >= 1e-3 else height(characters, body) or 1.0


def at_point(fx, shape, euler) -> int:
    """W6 for a body without a hand, on the staged ``fx.xbr`` document
    ``fx``: each staff end of every staff graph stays unbound (the body
    has no ``m_stafftop`` / ``m_staffbottom``) and takes its power head's
    map whole (``shape``, :func:`~azurik_mod.patches._player_power_fx.point_shape`:
    at the body's action point moved outside it, upright, sized to it;
    Step 2.182, D707; ``euler`` the XBE's tables), and the staff's blades
    under it shrink to 0.001, as on a body with hands.  Returns the meshes
    shrunk."""
    from azurkit.tools.characters import _player_power_fx as power

    hidden = power.blades(fx.raw)
    power.reshape(fx, shape, euler, bound=False)
    return sum(_shrink(fx, recs, end, hidden) for recs, ends in _staff_graphs(fx.raw) for end in ends.values())


def power_shape(game, characters: bytes | None, body: Body, lo: Loadout | None, point: ActionPoint | None):
    """W6's power heads on ``body`` and its loadout ``lo`` (Step 2.182,
    D707: :mod:`~azurik_mod.patches._player_power_fx`'s look B): on a
    carried prop's carriers (the hoe, :attr:`Loadout.fx_ends`), else on
    its action point's hands, else at its point (outside its mesh in
    ``characters``), and the XBE's Euler tables."""
    from azurkit.tools.characters import _player_power_fx as power

    euler = Euler(bytes(game["default.xbe"]))
    if lo is not None and lo.fx_ends:   # the prop's mesh as the disc holds it (W26 turns the farmers')
        return power.hoe_shape(game.stored("characters.xbr"), lo.prop, lo.k), euler
    if point.hands:
        from azurkit.tools.characters._player_weapons import weapons

        skip = {n for w in weapons().values() if w.prop is not None   # a carried prop's carriers aren't the fist
                for n in (*w.prop.carriers, *(w.prop.own_carriers or ()))}
        return power.hand_shape(characters, body.name, point.hands, skip), euler
    tall = body_height(characters, body)
    return power.point_shape(point.point, point.kind == "marker", tall / read_body(characters, PLAYER).top,
                             mesh_bounds(characters, body.name), tall), euler


# --- W15: the armor sits on the body (Step 2.77b) ---------------------------
ARMOR_FX = ("fx/magic/fx_jump", "fx/magic/fx_light", "fx/magic/fx_shield_")
"""The armors' ``fx.xbr`` graphs, the ones ``config.xbr``'s ``magic``
table casts on the player: the air armor's wings (``fx_jump1``-``3``),
the light armor and the four shields."""


def _xform_ancestors(buf, xforms: dict[int, int], rec: int) -> set[int]:
    """The indexes of the transform record ``rec``'s ancestors among
    ``xforms`` (index -> record offset; a record's parent index is at
    +0x18), up to the first that isn't a transform."""
    out: set[int] = set()
    while True:
        (p,) = struct.unpack_from("<i", buf, rec + 0x18)
        if p not in xforms or p in out:
            return out
        out.add(p)
        rec = xforms[p]


def fit_armor(fx, characters: bytes, body: Body) -> int:
    """W15 on the staged ``fx.xbr`` document ``fx``: in each armor graph
    (:data:`ARMOR_FX`) a transform bound to a node of garret4's body that
    ``body`` lacks (by exact name, as 0xCA1D0 looks it up: ``m_skull``,
    ``m_chest``, ``m_root``, ``m_waist``, the shoulders, wrists and
    ankles) stays unbound at its authored translate and scale: garret4's
    point, in the player's model, which the critter's scale then scales
    (the 2.75a sitting: the air armor's wings far above keylord at x2 and
    flicken).  Each such transform (no pivots, under the graph's root)
    gets both times the body's height over garret4's
    (:func:`body_height`), so the helm, breastplate and wings sit on the
    body at his proportions, sized to it.  A descendant at inherit mode 1
    (the force shield's ``ForceField`` and the electric shield's ``Zaps``,
    no pivots) takes only the translation that carries its anchor
    (0x681E0), dropping that scale, so its own scale gets the same factor.
    ``m_jump`` (X16 poses it) and the staff ends (W6) are left alone.
    A transform bound to one of :data:`ARMOR_NODES` that the body has
    (m_root on 11 bodies, m_waist on blaze_sentinel) is sized the same
    way, since X16 binds it to a bone of the body too (Step 2.118,
    AZ-448: guard_air's force bubble was 0.36 x its size).  Returns the
    transforms written."""
    garret4 = read_body(characters, PLAYER)
    lacks = ({*garret4.markers, *(n for n, _ in garret4.bones)} - {*body.markers, *(n for n, _ in body.bones)}
             - {WINGS_MARKER, *STAFF_BINDS})
    if body.name.casefold() != PLAYER:
        lacks |= set(ARMOR_NODES)
    k = body_height(characters, body) / garret4.top
    names = named_resources(fx.raw)
    written = 0
    for entry in parse_toc(fx.raw):
        if entry.tag != "node" or not names.get(entry.index, "").startswith(ARMOR_FX):
            continue
        recs = record_offsets(fx.raw, entry.file_offset)
        xforms = {i: rec for i, rec in enumerate(recs) if rec is not None and lstr(fx.raw, rec) == "transform"}
        moved = {i for i, rec in xforms.items() if bind_name(fx.raw, rec) in lacks}
        for i, rec in xforms.items():
            mode1 = (i not in moved and struct.unpack_from("<I", fx.raw, rec + 0x28)[0] == 1
                     and bool(moved & _xform_ancestors(fx.raw, xforms, rec)))
            if i not in moved and not mode1:
                continue
            attrs, _ = list_at(fx.raw, rec + 8)
            old = bytes(fx.raw[attrs + 4:attrs + 40])
            t, r, s = (struct.unpack_from("<3f", old, 12 * j) for j in range(3))
            t = t if mode1 else tuple(v * k for v in t)
            replace_bytes_at(fx, attrs + 4, struct.pack("<9f", *t, *r, *(v * k for v in s)), expected=old)
            written += 1
    return written


# --- X4: the roll moves (Step 2.21b) --------------------------------------
ROLL_HOOK_VA = 0x8C6AE
"""player_attack_root_motion's CALL of the root-motion sampler 0xCACD0
(``anim_root_motion_delta``), which X4 replaces."""
_ROLL_HOOK_VANILLA = bytes.fromhex("e81de60300")    # CALL 0xCACD0
ROLL_SHIM = ShimSource(folder=Path(__file__).resolve().parent / "player_model", stem="roll")
ROLL_SHIM_NAME = "player_model_roll"
"""Its object's name: ``player_model_roll.o`` in the shim build dir."""
ROLL_HOOK = TrampolinePatch(
    name=ROLL_SHIM_NAME,
    label=f"Player model roll: garret4's root motion (X4) at VA 0x{ROLL_HOOK_VA:X}",
    va=ROLL_HOOK_VA,
    replaced_bytes=_ROLL_HOOK_VANILLA,
    shim_object=ROLL_SHIM.object_path(ROLL_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_roll",
)


def _install(xbe: bytearray, hook: TrampolinePatch, shim: ShimSource, what: str,
             params: dict[str, float | bytes] | None = None) -> None:
    """Hook ``shim`` into ``xbe`` at ``hook`` (with its float or bytes ``params``),
    releasing the shim session the apply opens (it holds ``xbe``).  A
    hook already holding it writes nothing (one with float params
    raises); one holding anything but vanilla's CALL, or a shim that
    doesn't build, raises :class:`ValueError` naming ``what`` (D35)."""
    try:
        ok = apply_trampoline_patch(xbe, hook, repo_root=CHECKOUT, params=params,
                                    shim_source=shim.source_path())
    finally:
        release_session(xbe)
    if not ok:
        raise ValueError(f"the {what} shim at VA 0x{hook.va:X} didn't install "
                         "(the line above says why)")


def install_roll_shim(xbe: bytearray) -> None:
    """Install X4 (``player_model/roll.c``) at VA 0x8C6AE in ``xbe``:
    during 'roll forward' the sampler hands back garret4's ``m_feet``
    motion over the same fraction of the clip, so the roll travels
    garret4's distance in the model's own roll time; every other move
    samples as before (:func:`_install`)."""
    _install(xbe, ROLL_HOOK, ROLL_SHIM, "roll")


# --- X7: the hit reaction lasts garret4's (Step 2.21d) ----------------------
HIT_HOOK_VA = 0x8D682
"""The player's hit handler's (0x8D600) CALL of anim_change_at_node
(0x42750), its only caller, which X7 replaces."""
_HIT_HOOK_VANILLA = bytes.fromhex("e8c950fbff")     # CALL 0x42750
HIT_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="hit_reaction")
HIT_SHIM_NAME = "player_model_hit_reaction"
"""Its object's name: ``player_model_hit_reaction.o`` in the shim build dir."""
HIT_SECONDS = FloatParam(
    name="hit_seconds", symbol="_player_model_hit_seconds", default=0.4,
    label="Player model hit reaction length (X7)",
    description="How long a hit reaction lasts, s: garret4's 0.4; 0 (no build writes it since Step "
                "2.129) plays the reaction the game picks at its own length.")
HIT_HOOK = TrampolinePatch(
    name=HIT_SHIM_NAME,
    label=f"Player model hit reaction: garret4's 0.4 s (X7) at VA 0x{HIT_HOOK_VA:X}",
    va=HIT_HOOK_VA,
    replaced_bytes=_HIT_HOOK_VANILLA,
    shim_object=HIT_SHIM.object_path(HIT_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_hit@16",
    float_params=(HIT_SECONDS,),
)


# --- X8: the camera aims at the body, not its feet (Step 2.23c) -------------
EYE_HOOK_VA = 0x41F67
"""The critter camera point's (0x41F40, its vtable slot +0xB0, which only
the cameras call) CALL of the marker lookup 0xCB2A0 for ``m_head``, which
X8 replaces."""
_EYE_HOOK_VANILLA = bytes.fromhex("e834930800")    # CALL 0xCB2A0
EYE_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="eye")
EYE_SHIM_NAME = "player_model_eye"
"""Its object's name: ``player_model_eye.o`` in the shim build dir."""
EYE_HEIGHT = FloatParam(
    name="eye_height", symbol="_player_model_eye_height", default=0.0,
    label="Player model camera point (X8)",
    description="The height, in the body's model units, of the point the cameras aim "
                "at on the player: garret4's fraction of its mesh's top.")
EYE_LAND = FloatParam(
    name="eye_land", symbol="_player_model_eye_land", default=1.0,
    label="Player model camera point on land (X8)",
    description="1: X8's point out of the water too; 0: the game's m_head there, X8's swim point only "
                "(garret4's own body drawn under x1, Step 2.126).")
EYE_MARGINS = BytesParam(
    name="swim_margin", symbol="_player_model_swim_margin", size=8,
    label="Player model camera point swimming (X8)")
"""X8's two swim margins, two f32, in metres: over the water the point the
cameras aim at is at least the first's under the surface (negative: over
it), which keeps the camera that high over the water (Step 2.116), and
once the swimming body's top is under it is the second's under it
(:func:`swim_margins`; the object's own 0.5 and 3.5 without a rig)."""
SWIM_MARGINS = (0.5, 3.5)
"""X8's object's own swim margins (Step 2.80b): the camera 2 m over the
water, then 1 m under it, at the game's 5 m rest distance."""
EYE_OVER_FEET = BytesParam(
    name="over_feet", symbol="_player_model_over_feet", size=36,
    label="Player model camera point over a ladder's top and a hoist (X8)")
"""X8's climb-over offsets, three rows of three f32 in model units (Step
2.116; the hoists, Step 2.127): on a baked body with clips
(:func:`own_grab`) garret4's ``m_feet`` at the end of climb_up_edge, hoist and hoist_waist
(:data:`G4_OVER_ROWS`, :func:`over_rows`), which the point gains over
each glide; zeros elsewhere, which keep the land point there and in the
stance."""
G4_OVER_FEET = (0.0, 1.36404443, 2.26890564)
"""garret4's ``m_feet`` in climb_up_edge (anim 0x3F; constant over the
clip; model units, x right, y forward, z up): X23's ``g4_feet``, and
X8's first row on a baked body."""
G4_HOIST_FEET = (0.0, 1.22300005, 1.77436328)
"""garret4's ``m_feet`` at hoist's end (anim 0x41, a tall ledge; from
(0, -0.003, 0.111) at its start): X23's ``g4_hoist_feet``, X8's second
row (Step 2.127, AZ-572)."""
G4_WAIST_FEET = (0.0, 0.701313615, 1.00312757)
"""garret4's ``m_feet`` at hoist_waist's end (anim 0x42; from (0, 0.211,
-0.192)): X23's ``g4_waist_feet``, X8's third row (Step 2.127)."""
G4_OVER_ROWS = (G4_OVER_FEET, G4_HOIST_FEET, G4_WAIST_FEET)
"""X8's :data:`EYE_OVER_FEET` on a baked body with clips."""


EYE_OVER_TIMER = FloatParam(
    name="over_timer", symbol="_player_model_over_timer", default=0.0,
    label="Player model camera point on a body with no clips (X8)",
    description="1 / the drawn scale on a body with no clips, whose bone rides garret4's m_feet / D "
                "(Step 2.127): the point takes that times its m_feet marker; 0 elsewhere.")


def over_rows(body: Body) -> tuple[tuple[float, float, float], ...] | None:
    """X8's :data:`EYE_OVER_FEET` rows for ``body``: garret4's three on a
    baked body with clips (:data:`G4_OVER_ROWS`), ``None`` (zeros) for a
    body on X9's stand-ins and one with no clips (:func:`over_timer`'s)."""
    return G4_OVER_ROWS if own_grab(body) and body.clips else None


def over_timer(body: Body, drawn: float) -> float:
    """X8's :data:`EYE_OVER_TIMER` for ``body`` drawn ``drawn`` times its
    model: 1 / ``drawn`` on a body with no clips (its root rides garret4's
    ``m_feet`` / D, so its top over the drawn origin is the top plus its
    ``m_feet`` marker / D in model units, which X8 reads: Step 2.127,
    AZ-562), else 0."""
    return 1.0 / drawn if not body.clips and own_grab(body) and drawn and math.isfinite(drawn) else 0.0


EYE_HOOK = TrampolinePatch(
    name=EYE_SHIM_NAME,
    label=f"Player model camera: the top of the body (X8) at VA 0x{EYE_HOOK_VA:X}",
    va=EYE_HOOK_VA,
    replaced_bytes=_EYE_HOOK_VANILLA,
    shim_object=EYE_SHIM.object_path(EYE_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_eye",
    float_params=(EYE_HEIGHT, EYE_LAND, EYE_OVER_TIMER),
    bytes_params=(EYE_MARGINS, EYE_OVER_FEET),
)


# --- X10: the attacks rotate (Step 2.64) ----------------------------------
ROTATE_HOOK_VA = 0x889A6
"""player_attack_enter's (0x88990) CALL of anim_change (0x42910), which
plays an attack's clip and which X10 replaces."""
_ROTATE_HOOK_VANILLA = bytes.fromhex("e8659ffbff")    # CALL 0x42910
ROTATE_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="attack_rotation")
ROTATE_SHIM_NAME = "player_model_attack_rotation"
"""Its object's name: ``player_model_attack_rotation.o`` in the shim build dir."""
ROTATE_HOOK = TrampolinePatch(
    name=ROTATE_SHIM_NAME,
    label=f"Player model attacks: one clip per swing in turn (X10) at VA 0x{ROTATE_HOOK_VA:X}",
    va=ROTATE_HOOK_VA,
    replaced_bytes=_ROTATE_HOOK_VANILLA,
    shim_object=ROTATE_SHIM.object_path(ROTATE_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_attack@12",
)
RING_COLUMNS = 24
"""The columns the ring holds: ``attacks_anims``' 24."""
RING_ENTRY = struct.Struct(f"<ifff{RING_COLUMNS}f")
"""One ring entry in the shim's ``RingEntry``: the column whose slot holds
its clip, (Step 2.69) the Rate a swing takes from it when the ring
carries its numbers, (Step 2.104, AZ-523) its chain point's two terms
(W19's, :func:`chain_terms`: the swing chains at ``hit`` + ``after`` x
the Rate it plays at, as fractions of its clip; ``after`` 0.0 keeps the
column's) and the Damage multiplier its clip deals in each column, when
the ring carries them."""
_RING_HEAD = struct.Struct("<iiIII")
"""The shim's ``Ring`` before its entries: the count, the next entry (0 at
boot, D227), the columns that rotate, whether a swing takes its
entry's Damage multiplier and Rate (nonzero) or keeps its column's, and
the columns whose swings take its chain point too (W19's, Step 2.104)."""
RING_SIZE = _RING_HEAD.size + RING_COLUMNS * RING_ENTRY.size


def install_rotate_shim(xbe: bytearray, ring: list[int], columns: int,
                        carry: list[tuple[float, list[float]]] | None = None,
                        chains: list[tuple[float, float]] | None = None, chained: int = 0) -> int:
    """Install X10 (``player_model/attack_rotation.c``) at VA 0x889A6 in
    ``xbe`` and write its ring into the ``.data`` it landed with: each
    swing of the player in one of ``columns`` (a mask) plays the clip of
    the next column of ``ring`` (:func:`rotation`), and with ``carry``
    (per ring entry its Rate and the Damage multiplier its clip deals in
    each of the 24 columns: the attack balance, Step 2.69) takes the
    entry's Rate and its multiplier for the swinging column into its
    PlayerControl (+0x104, +0xEC) too, and with ``chains`` (per ring entry
    its chain point's terms, :func:`chain_terms`) a swing in a column of
    ``chained`` (a mask: own body's basic1-3, W19, Step 2.104, AZ-523)
    writes its entry's chain point at the Rate it plays at into +0xFC,
    unless the entry's ``after`` is 0.0; every other anim_change call is
    the game's (:func:`_install`).  Returns the ring's VA (X38 reads its
    place).  :class:`ValueError` when the landed ``.data`` isn't the
    ring's size or ``carry`` or ``chains`` doesn't fit it (D35)."""
    _install(xbe, ROTATE_HOOK, ROTATE_SHIM, "attack-rotation")
    spans = [span for span in trampoline_shim_data(xbe, ROTATE_HOOK, CHECKOUT,
                                                   shim_source=ROTATE_SHIM.source_path())
             if span[1] - span[0] == RING_SIZE]
    if len(spans) != 1 or len(ring) > RING_COLUMNS:
        raise ValueError(f"the attack-rotation shim at VA 0x{ROTATE_HOOK_VA:X} landed no "
                         f"{RING_SIZE}-byte ring for {len(ring)} entries")
    if (carry is not None and (len(carry) != len(ring) or any(len(m) != RING_COLUMNS for _, m in carry))
            or chains is not None and len(chains) != len(ring)):
        raise ValueError(f"the attack-rotation ring's numbers don't fit its {len(ring)} entries "
                         f"of {RING_COLUMNS} columns")
    at = resolve_va_to_file(xbe, spans[0][0])
    numbers = carry or [(0.0, [0.0] * RING_COLUMNS)] * len(ring)
    terms = chains or [(0.0, 0.0)] * len(ring)
    data = _RING_HEAD.pack(len(ring), 0, columns, int(carry is not None), chained if chains else 0) + b"".join(
        struct.pack("<i", c) + pack_f32(r) + pack_f32(h) + pack_f32(a) + b"".join(pack_f32(v) for v in m)
        for c, (r, m), (h, a) in zip(ring, numbers, terms))
    xbe[at:at + RING_SIZE] = data.ljust(RING_SIZE, b"\0")
    return spans[0][0]


def install_eye_shim(xbe: bytearray, top: float, margins: tuple[float, float] = SWIM_MARGINS,
                     over_feet: tuple[tuple[float, float, float], ...] | None = None, timer: float = 0.0,
                     land: bool = True) -> None:
    """Install X8 (``player_model/eye.c``) at VA 0x41F67 in ``xbe``: the
    player's camera point is ``top`` (model units; the game scales it by
    the critter's +0x188) above its feet, where garret4's ``m_head`` sits
    on his body (:func:`camera_plan`), except while it swims (its
    PlayerControl in move state 6): then, measured from its model origin
    (critter_model_matrix, 0x42200) against the surface (critter+0x15C
    plus its depth, +0x27C; AZ-413), the point is ``top`` raised to no
    lower than ``margins[0]`` m under the surface while it is on the
    water's top side (Step 2.116, AZ-311), and ``margins[1]`` m under it
    once the top is under, never above the top, so the camera goes under
    with it; the side changes only 0.25 m past the surface (AZ-414), and
    under only in a dive, +0x15C deeper than 2.55 m, back over at 2.35 m
    (garret4's own crossing depths; Steps 2.116, 2.116b) (:func:`swim_margins`; the object's own 0.5 and 3.5
    without a rig).  With ``over_feet`` (a baked body's rows,
    :func:`over_rows`; Step 2.116, the hoists Step 2.127) the point gains
    a row x the glide's fraction over climb_up_edge's, hoist's or
    hoist_waist's glide, and less 0x402E0's term while the stance's hold
    is on after one with a row (X26's rule), so it rises with the body
    over a ladder's top or a ledge and holds through the stance; with a
    ``timer`` (:func:`over_timer`, a body with no clips, no rows) the
    point gains ``timer`` x its ``m_feet`` marker (0xCB2A0) out of the
    water, so it rides the prop's top in every clip.  Not ``land``
    (swim-only, Step 2.126, D319: garret4's own body drawn under x1), the
    point out of the water is the game's ``m_head``.  Every other
    critter's is as before (:func:`_install`)."""
    rows = over_feet or ((0.0, 0.0, 0.0),) * 3
    _install(xbe, EYE_HOOK, EYE_SHIM, "camera",
             {EYE_HEIGHT.name: top, EYE_LAND.name: 1.0 if land else 0.0, EYE_OVER_TIMER.name: timer,
              EYE_MARGINS.name: b"".join(pack_f32(m) for m in margins),
              EYE_OVER_FEET.name: b"".join(pack_f32(f) for row in rows for f in row)})


# --- X9: the ladder latches, climbs and lets go (Step 2.63) -----------------
def _call(va: int, target: int) -> bytes:
    """The 5-byte ``CALL target`` at ``va``."""
    return b"\xe8" + struct.pack("<i", target - (va + 5))


CLIMB_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="climb")
CLIMB_SHIM_NAME = "player_model_climb"
"""Its object's name: ``player_model_climb.o`` in the shim build dir."""
CLIMB_SCALE = FloatParam(
    name="climb_scale", symbol="_player_model_climb_scale", default=1.0,
    label="Player model zipline hang scale (X9)",
    description="How many times garret4's m_grab offset below the cable the zipline ride and hang_start "
                "hang the body: 1 at x1, else where the top of its drawn hang pose sits 0.05 m under the "
                "cable, as garret4's does (hang_scale).")
CLIMB_GRAB = FloatParam(
    name="climb_grab", symbol="_player_model_climb_grab", default=0.0,
    label="Player model zipline own grab (X9)",
    description="1 when the game already hangs the body's own m_grab on the cable (a baked body), else 0.")
HANG_HOOKS = ("ride", "hang")
"""X9's landings that hang the body from the zipline, which take
:data:`CLIMB_SCALE` and :data:`CLIMB_GRAB` (Step 2.104, AZ-526)."""
CLIMB_HOOKS = tuple(TrampolinePatch(
    name=f"{CLIMB_SHIM_NAME}_{what}",
    label=f"Player model climb: {why} (X9) at VA 0x{va:X}",
    va=va,
    replaced_bytes=_call(va, target) if isinstance(target, int) else target,
    shim_object=CLIMB_SHIM.object_path(CLIMB_SHIM_NAME, CHECKOUT),
    shim_symbol=symbol,
    float_params=(CLIMB_SCALE, CLIMB_GRAB) if what in HANG_HOOKS else (),
) for what, why, va, target, symbol in (
    ("move", "a stand-in clip for an aligned move, in garret4's time", 0x8BDF3, 0x42430,
     "_c_player_model_climb_move@36"),
    ("loop", "a stand-in clip for a climb loop, on garret4's rung", 0x883CB, 0x42910,
     "_c_player_model_climb_loop"),
    ("idle", "a stand-in clip for climb_idle, on garret4's rung", 0x88733, 0x42910,
     "_c_player_model_climb_idle"),
    ("touchdown", "a stand-in clip for the hard landing, in garret4's time", 0x8B0D4, 0x42430,
     "_c_player_model_climb_move@36"),
    ("landing", "a stand-in clip for the hard landing, in garret4's time", 0x8B18C, 0x42430,
     "_c_player_model_climb_move@36"),
    ("hang", "a stand-in clip for the overhead hang, in garret4's time", 0x8A4E3, 0x42430,
     "_c_player_model_climb_move@36"),
    ("use", "a stand-in for a victory or use the body has no clip for", 0x888C2,
     bytes(8), "_c_player_model_climb_use"),
    ("victory", "a stand-in clip for a victory or use, in garret4's time", 0x88951, 0x42430,
     "_c_player_model_climb_move@36"),
    ("immune", "garret4's hit immunity for a stand-in's victory or use", 0x88958,
     bytes(9), "_c_player_model_climb_immune"),
    ("ride", "the zipline ride, hanging where garret4 does", 0x8AB32, 0x42E40,
     "_c_player_model_climb_ride"),
    *((f"rate_{move}", f"garret4's time for a short stand-in's {move}, at its rate", va, 0x30940,
       "_c_player_model_climb_rate")
      for move, va in (("hoist", 0x86D9E), ("latch", 0x870F7), ("jump_latch", 0x87444),
                       ("down_edge", 0x87929), ("up_edge", 0x87F55), ("step_up", 0x8B6CD))),
))
"""X9's hooks, one landing each of ``player_model/climb.c``: the move-state
setter's CALL of the aligned clip change 0x42430 (0x8BDF3), the climb
tick's two CALLs of anim_change (0x883CB in 0x87F80, 0x88733 in 0x88490),
the hard landing's (0x8B0D4, 0x8B18C) and the overhead hang's (0x8A4E3)
CALLs of 0x42430 (Step 2.66b), the victory and use move's (0x887D0) check
of its slot (0x888C2), CALL of 0x42430 (0x88951) and load of the clip's
length for the hit timer (0x88958; Step 2.103, AZ-444), the zipline
ride's CALL of anim_apply_translation 0x42E40 (0x8AB32; Step 2.103,
AZ-443: the cable point moved down by garret4's ``m_grab``), and the CALL of
the layer-rate setter 0x30940 each of the setter's six callers makes
right after it (Step 2.96, AZ-489: a stand-in shorter than garret4's
clip plays at that rate x its length over his)."""
_CLIMB_STAND_INS = ("idle", "idle_1", "walk", "run")
"""X9's stand-in for a clip the body lacks: the first of these it has, else
the clip its roll plays."""
_CLIMB_CLIPS = ("climb_start", "climb_from_jump", "climb_down_edge", "climb_up_edge", "climb_idle",
                "climb_up", "climb_down", "climb_left", "climb_right", "hoist", "hoist_waist", "step_up")
"""The clips the setter's moves and the climb tick play (garret4's body has
them all, and no other body any)."""


def needs_climb_shim(body: Body) -> bool:
    """Whether ``body`` needs X9: it has clips, so a stand-in, but lacks one
    the ladder, the hoist or the step out of the water plays, and has no
    ``m_grab`` marker for the rungs (every body with clips but garret4's
    and one B bakes, which gains ``m_grab`` and plays his baked climb
    clips)."""
    return (bool(body.clips) and "m_grab" not in body.markers
            and not set(_CLIMB_CLIPS) <= set(body.clips))


def install_climb_shim(xbe: bytearray, model_scale: float = 1.0) -> None:
    """Install X9 (``player_model/climb.c``) at its sixteen hooks in ``xbe``:
    for the player's species, an aligned move (the ladder's, the hoist's,
    the step's, the hard landing's, the hang's, a victory or the use) or a
    climb loop whose clip the body lacks plays its stand-in (idle, else
    idle_1, walk, run, the roll's clip), an aligned move in garret4's time
    and ending where his does (a victory or use with his hit immunity), and
    on the rungs and the zipline the body sits where garret4 does (by his
    ``m_grab``; on the zipline ``model_scale`` times his offset: the body
    drawn at a model scale, :func:`hang_scale`'s; Step 2.104, AZ-526;
    Step 2.106, AZ-529; :func:`_install`)."""
    for hook in CLIMB_HOOKS:
        _install(xbe, hook, CLIMB_SHIM, "climb",
                 {CLIMB_SCALE.name: model_scale, CLIMB_GRAB.name: 0.0} if hook.float_params else None)


def own_grab(body: Body) -> bool:
    """Whether a body hangs and climbs on an ``m_grab`` of its own (a baked
    body gains garret4's), not X9's stand-ins."""
    return "m_grab" in body.markers and not needs_climb_shim(body)


def needs_hang_shim(body: Body, model_scale: float) -> bool:
    """Whether a body X9 doesn't serve needs its zipline landings alone
    (Step 2.104, AZ-526): it hangs from an ``m_grab`` of its own
    (:func:`own_grab`), which the game puts on the cable unscaled,
    and it is drawn at a model scale other than 1, so its drawn hands sit
    that scale less 1 times the offset off the cable."""
    return model_scale != 1.0 and own_grab(body)


def install_hang_shim(xbe: bytearray, model_scale: float) -> None:
    """Install X9's zipline landings (``player_model/climb.c``, the ride at
    0x8AB32 and hang_start at 0x8A4E3) in ``xbe`` for a body with its own
    ``m_grab`` drawn at a model scale (:func:`needs_hang_shim`): the ride
    moves the cable point down by (``model_scale`` - 1) x garret4's
    ``m_grab`` and hang_start's glide ends that much lower, so the drawn
    hang pose's top sits where garret4's does (``model_scale``
    :func:`hang_scale`'s; :func:`_install`)."""
    for hook in CLIMB_HOOKS:
        if hook.float_params:
            _install(xbe, hook, CLIMB_SHIM, "climb", {CLIMB_SCALE.name: model_scale, CLIMB_GRAB.name: 1.0})


CLIMB_OFFSETS_HOOK = TrampolinePatch(
    name=f"{CLIMB_SHIM_NAME}_offsets",
    label="Player model climb: garret4's ladder offsets where the body has none (X9) at VA 0x84E59",
    va=0x84E59,
    replaced_bytes=_call(0x84E59, 0x84A40),
    shim_object=CLIMB_SHIM.object_path(CLIMB_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_climb_offsets@4",
)
"""X9's offsets hook (Step 2.63b): the PlayerPhysics constructor's CALL of
player_move_offsets_init (0x84A40)."""
CLIMB_OFFSETS = (0x38A610, 0x389B78, 0x38B0D0)
"""0x84A40's arrays (USA): m_root, m_feet and m_grab at both ends of each
clip slot, 0x18 bytes a slot."""
CLIMB_OFFSETS_TABLE = "_player_model_climb_offsets_at"


def needs_climb_offsets(body: Body) -> bool:
    """Whether ``body`` needs X9's offsets hook: 0x84A40 would leave the
    ladder's offsets zero, as it lacks the ladder's clips (X9's bodies) or
    garret4's ``m_root`` (every baked body but the air elemental)."""
    return "m_root" not in body.markers or needs_climb_shim(body)


def install_climb_offsets(xbe: bytearray) -> None:
    """Install X9's offsets hook (``player_model/climb.c``) at VA 0x84E59
    in ``xbe`` and write the arrays' addresses, as ``xbe``'s release has
    them, into it: each ladder offset 0x84A40 leaves (0, 0, 0)
    takes garret4's, so a swapped body latches onto a ladder
    (:func:`_install`)."""
    _install(xbe, CLIMB_OFFSETS_HOOK, CLIMB_SHIM, "climb offsets")
    at = resolve_va_to_file(xbe, trampoline_symbol_va(xbe, CLIMB_OFFSETS_HOOK, CLIMB_OFFSETS_TABLE, CHECKOUT,
                                                      shim_source=CLIMB_SHIM.source_path()))
    xbe[at:at + 12] = struct.pack("<3I", *map(xbe_layout(xbe).va, CLIMB_OFFSETS))


# --- X13: the attack box's reach and reach-to-ground (Step 2.70) -----------
ATTACK_BOX_HOOK_VA = 0x43B47
"""The damage pass's (0x43A80) CALL of 0xCA390 (``anim_marker_box``),
which builds a damage marker's box in model units, and which X13
replaces."""
_ATTACK_BOX_HOOK_VANILLA = bytes.fromhex("e844680800")    # CALL 0xCA390
ATTACK_BOX_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="attack_box")
ATTACK_BOX_SHIM_NAME = "player_model_attack_box"
"""Its object's name: ``player_model_attack_box.o`` in the shim build dir."""
ATTACK_REACH = FloatParam(
    name="attack_reach", symbol="_player_attack_reach", default=1.0,
    label="Player model attack reach (X13)",
    description="How many times as far the player's hit boxes reach: each box's centre "
                "moves that many times as far ahead and the box grows that many times.")
ATTACK_GROUND = FloatParam(
    name="attack_ground_mask", symbol="_player_attack_ground_mask", default=0.0,
    label="Player model attack columns filled to the feet and the ground (X13)",
    description="The attacks_anims columns (bit i: column i) whose box X13 fills: its "
                "bounds, back to the feet, across the facing line and down to the "
                "floor; 0 fills none.")
ATTACK_BUMP_MASK = FloatParam(
    name="attack_bump_mask", symbol="_player_attack_bump_mask", default=0.0,
    label="Player model attack columns whose reach is bumped (X13)",
    description="The attacks_anims columns (bit i: column i) whose box reaches "
                "attack_bump times farther still: the attack balance's short melee "
                "columns (D223, Step 2.69); 0 bumps none.")
ATTACK_BUMP = FloatParam(
    name="attack_bump", symbol="_player_attack_bump", default=1.0,
    label="Player model attack reach bump (X13)",
    description="How many times farther the columns of attack_bump_mask reach (D223's "
                "bump, REACH_BUMP).")
ATTACK_BOX_HOOK = TrampolinePatch(
    name=ATTACK_BOX_SHIM_NAME,
    label=f"Player model attack box: reach and fill (X13) at VA 0x{ATTACK_BOX_HOOK_VA:X}",
    va=ATTACK_BOX_HOOK_VA,
    replaced_bytes=_ATTACK_BOX_HOOK_VANILLA,
    shim_object=ATTACK_BOX_SHIM.object_path(ATTACK_BOX_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_attack_box",
    float_params=(ATTACK_REACH, ATTACK_GROUND, ATTACK_BUMP_MASK, ATTACK_BUMP),
)
GROUND_COLUMNS = 24
"""The columns X13's mask holds: a float holds every whole number below
2^24 exactly, and ``attacks_anims`` has 24 (the roll's among them)."""


def is_melee(windows: tuple[DamageWindow, ...], model_scale: float = 1.0) -> bool:
    """Whether an attack whose clip has ``windows`` is melee: Step 2.61's
    rule, every box of it reaches at most :data:`MELEE_REACH` (4.0 m)
    from the feet, times ``model_scale`` for boxes drawn that many times
    their size (the logic's rule, :func:`melee_reach`, AZ-559: so a box's
    class is its x1 one); a clip with no window, which builds no box of
    its own, counts as melee."""
    limit = MELEE_REACH * abs(model_scale)
    return all(w.reach <= limit for w in windows)


def fill_mask(columns: list[str]) -> int:
    """X13's fill (Step 2.132, AZ-605): bit i for each ``attacks_anims``
    column i but the roll, melee or ranged, each box's own or X3's
    (D347: an attack hits an enemy in front of the player down to the
    ground, a big body's too).  :class:`ValueError` when the table has
    more columns than the mask holds."""
    if len(columns) > GROUND_COLUMNS:
        raise ValueError(f"attacks_anims has {len(columns)} columns; X13's mask holds {GROUND_COLUMNS}")
    return sum(1 << i for i, col in enumerate(columns) if col != ROLL)


def install_attack_box_shim(xbe: bytearray, reach: float, mask: int, bump: int = 0) -> None:
    """Install X13 (``player_model/attack_box.c``) at VA 0x43B47 in
    ``xbe``: the player's hit boxes reach ``reach`` times as far, and
    :data:`REACH_BUMP` times farther still in a column of ``bump`` (the
    attack balance's short melee columns, :func:`weigh_attacks`); the box
    of an attack in a column of ``mask`` (:func:`fill_mask`) is filled:
    its bounds, back to the feet, across the facing line and down to the
    floor (Step 2.132); every other critter's box is the game's
    (:func:`_install`)."""
    _install(xbe, ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, "attack-box",
             {ATTACK_REACH.name: reach, ATTACK_GROUND.name: float(mask),
              ATTACK_BUMP_MASK.name: float(bump), ATTACK_BUMP.name: REACH_BUMP if bump else 1.0})


# --- W14: the attack balance, its damage and speed sliders (Step 2.69) -----
MULTIPLIER = "Damage multiplier"
"""``attacks_anims``' row the player's hit multiplies its damage by:
ceil(D x M), D the target's ``critters_damage`` value for the power's
type and level (Step 2.61; an empty cell is 1.0)."""
BALANCE_FLOOR = 0.5
"""The least the balance multiplies an attack's damage by (D223: damage
never drops below a floor, so every target the logic needs stays
killable; D228)."""
BALANCE_CAP = 4.0
"""The most the balance multiplies an attack's damage by (D228): a
design constant, so one hit can't one-shot by accident, not a slider
clamp (the damage slider multiplies on top, D23)."""
REACH_BUMP = 1.25
"""D223's reach bump: a melee attack far below the norm reaches this many
times as far (X13), at most +25%."""
BUMP_BELOW = 0.75
"""Far below the norm: a melee attack whose own box reaches less than
this share of garret4's basic1 reach (2.77 m, so 2.08 m) gets
:data:`REACH_BUMP` (0.5 until Step 2.132, D345: fire_elemental's 1.55 m
basics, keylord's basic2 and overlord's boxes missed a target 1.5 m
ahead)."""
SLOW_RATIO = 2.0
"""A slow attacker (D345, D350; Step 2.132, AZ-614): a body whose basics
(basic1-3, :data:`CHAINED`, as the build plays them, X10's ring entries
for a basic it turns) chain on average at least this many times as late
as garret4's: each at W19's chain point (:func:`chain_ticks`, the swing
the combo plays), garret4's at his first damage tick + 0.2 s (11.0, 9.25
and 9.25 ticks, so 19.7 or more on average): 23 of 81 own bodies at x1.
The whole move (``AttackMove.ticks``, Step 2.132) flagged 58, kingkong
and the fire elemental among them, whose chained swings are about as
short as garret4's."""
SLOW_BONUS = 1.25
"""D350 (the owner: "A bit above Garret"): a slow attacker deals this
many times garret4's damage per second on one target
(:func:`combo_rate`, Step 2.138, AZ-614): every weighed attack's B,
after the 0.5-4.0 hold, is multiplied by the body's own factor,
garret4's rate x this over the body's at its B (never under 1.0), and
held to at most 5.0 (D350 amends D228's hold there).  Any other body
whose one-target rate is under garret4's takes garret4's rate over its
own the same way, held to D228's 4.0 (D389, Step 2.138: the fire
elemental x1.11, kingkong x1.89)."""
RECOVERY = 3.75
"""How long, in seconds, after a combo's finisher hits one target the
next combo's basic1 hits it again, which :func:`combo_rate` counts
(Step 2.132's record, row C3, a held sleeth pressed every 6 ticks: 112
ticks after garret4's finisher, 118 after guard_air's, 122 after the
fire elemental's, 99 after kingkong's; their mean)."""
FINISHERS = ("finish", "finish3")
"""The columns basic3 chains into (``attacks_transitions``), the combo's
finisher in :func:`combo_rate` (their mean)."""
HIT_TICKS = 10
"""How often one target takes a hit from a box that stays on it, in
ticks: the player's damage types' Delay, 0.33 s at 30 ticks a second
(Step 2.61)."""
ATTACK_DEFAULTS = {"garret4": (False, False), "own": (True, True)}
"""Each gameplay mode's attack balance and reach-to-ground (X13's fill)
when no option says (D222, D223, D225): own body both on; garret4's
exact (his boxes) neither."""


@dataclass(frozen=True)
class AttackMove:
    """One attack move as the balance weighs it: how many ticks it lasts,
    how many hits it lands on one target that stays in its boxes (one per
    :data:`HIT_TICKS`), and how far (m) its boxes reach from the feet."""

    ticks: float
    hits: int
    reach: float


def attack_move(rate: float, clip: float, window: tuple[float, float],
                windows: tuple[DamageWindow, ...] | None, x3_reach: float = 0.0) -> AttackMove | None:
    """The move a ``clip``-second clip makes from ``window[0]`` to
    ``window[1]`` of it (:func:`move_window`) at ``rate`` clip seconds a
    second, hitting through ``windows`` (in clip seconds: the speed slider
    moves them with the clip), or X3's box (reach ``x3_reach``) from
    :data:`X3_OPENS` to :data:`X3_CLOSES` of the move when ``windows`` is
    None; ``None`` for a move that takes no time."""
    start, end = window
    if rate <= 0 or clip <= 0 or end <= start:
        return None
    ticks = 30.0 * (end - start) * clip / rate
    if windows is None:
        spans, reach = [(X3_OPENS * ticks, X3_CLOSES * ticks)], x3_reach
    else:
        spans = []
        for w in windows:
            lo, hi = max(w.on, start * clip), min(w.off, end * clip)
            if hi >= lo:
                spans.append((30.0 * (lo - start * clip) / rate, 30.0 * (hi - start * clip) / rate))
        reach = max((w.reach for w in windows), default=0.0)
    hits, wait = 0, 0
    for tick in range(int(max((b for _, b in spans), default=-1)) + 1):
        if wait <= 0 and any(a <= tick <= b for a, b in spans):
            hits, wait = hits + 1, HIT_TICKS
        wait -= 1
    return AttackMove(ticks, hits, reach)


def balance_factor(norm: AttackMove | None, move: AttackMove | None, bump: float = 1.0) -> float | None:
    """D228's balance B for an attack ``move`` against garret4's ``norm``
    for the same column (2.61's formula): (its ticks / garret4's) x
    sqrt(garret4's reach / its reach x ``bump``) x (garret4's hits / its),
    held to :data:`BALANCE_FLOOR` and :data:`BALANCE_CAP`: damage over time
    evens out at equal reach, a shorter box hitting harder and a longer one
    softer, a slow attack more per hit and a fast one less.  ``None`` when
    either lands no hit."""
    if not (norm and move and norm.hits and move.hits and norm.reach > 0 and move.reach > 0):
        return None
    b = (move.ticks / norm.ticks) * math.sqrt(norm.reach / max(move.reach * bump, 0.05 * norm.reach)) \
        * norm.hits / move.hits
    return max(BALANCE_FLOOR, min(BALANCE_CAP, b))


def heavy_side(b: float | None, base: float) -> float | None:
    """D799 (AZ-774): the balance's ``b`` for a column whose vanilla
    ``Damage multiplier`` is ``base``, held so the multiplier the build
    writes, base x b, stays on garret4's side of the game's heavy-hit
    line.  The hit-level chooser 0x30BD0 makes a hit whose multiplier is
    under :data:`LIGHT` level 1 (0x30C11: ``FLD [ECX+0xC]``, ``FCOMP
    [0x1A250C]``, 1.0), a stun and a light flinch (a 0.30 s no-hit window:
    a sweep's contacts land twice), else takes its level from the damage
    against the target's ouch thresholds (``ouch2Threshold``: 5 in 71 of
    ``critters_critter_data``'s 108 columns), 2 or 3 a heavy one (2.55 s:
    one hit a swing).  A column garret4 hits heavy (``base`` 1.0 or more)
    keeps base x b at 1.0 or more, so its damage never drops under his:
    the least b that does where the balance gave less, its damage per
    second evened only on that side; a light one keeps its b (X18 stuns
    there at any multiplier, :func:`light_columns`).  ``None`` stays
    ``None``."""
    if b is None or base < LIGHT or base * b >= LIGHT:
        return b
    held = LIGHT / base
    while base * held < LIGHT:
        held = math.nextafter(held, math.inf)
    return held


def combo_rate(basics: list[tuple[float, float, float]], finisher: tuple[float, float]) -> float:
    """The damage per tick, in multiples of a target's damage for the
    hit, the combo deals one target that stays in its boxes, pressed as
    fast as it chains (D350's measure, Step 2.138, AZ-614): ``basics``
    (multiplier, first hit tick, chain tick) of basic1-3, each landing one
    hit before it chains (W19 chains 0.2 s after the hit, inside
    :data:`HIT_TICKS`), then ``finisher`` (multiplier, first hit tick),
    :data:`RECOVERY` after whose hit the next combo's basic1 hits: one
    combo lasts from basic1's hit to the next combo's."""
    (_, first, chain), *rest = basics
    return (sum(m for m, _, _ in basics) + finisher[0]) / (
        chain - first + sum(t for _, _, t in rest) + finisher[1] + 30.0 * RECOVERY)


@dataclass(frozen=True)
class Swing:
    """One swing of a combo on one target as W14 times it (Step 2.165b,
    D358's match): the Damage multiplier the build writes for it at the
    damage slider's 1 (garret4's x B), and in seconds into the move at the
    speed slider's 1 its first damage tick, its box's contact with the
    target ahead (:func:`_chain_at`) and the move's end; and, where W19
    times its column, its own ``Move end1`` before W19 (``None``: W19
    leaves the column, X10's ring and a borrowed move chaining at the
    point) and whether a contact, not the hit, times it (``met``)."""

    multiplier: float
    hit: float
    touch: float
    end: float
    kept: float | None = None
    met: bool = False

    def ticks(self, speed: float = 1.0) -> tuple[float, float]:
        """(first hit, W19's chain point) in ticks into the move at
        ``speed`` times its Rate (> 0), as :func:`chain_point` writes it:
        :data:`CHAIN_AFTER_HIT` after the hit or :data:`STUN_LAG` after
        the contact, which no speed scales; its own ``Move end1`` where
        W19 keeps it, after the hit and at most a tick past that point
        (a kit's swing, Step 2.159a, often chains there)."""
        hit, touch = self.hit / speed, self.touch / speed
        at = max(hit + CHAIN_AFTER_HIT, touch + STUN_LAG)
        chain = min(self.end / speed, at)
        if self.kept is not None and hit < (now := self.kept / speed) <= at + 1 / 30 and (
                not self.met or now >= touch + STUN_LAG):
            chain = now
        return 30.0 * touch, 30.0 * chain


@dataclass(frozen=True)
class Combo:
    """A body's combo on one target as W14 weighs it (Step 2.165b, D358's
    match-Garret buttons): garret4's mean chain point over basic1-3 (9.83
    ticks) and his one-target :func:`combo_rate`, and the body's swings
    in each of basic1-3 and the finishers (each column's played clips,
    X10's ring entries in a column it turns; ``None`` for one that hits
    nothing), the speed and damage sliders' 1."""

    norm_pace: float | None
    norm_rate: float | None
    basics: tuple[tuple[Swing | None, ...], ...]
    finishers: tuple[tuple[Swing | None, ...], ...]
    borrowed: bool = False
    """Whether a basic swings garret4's own move (:attr:`Loadout.borrowing`, Step
    2.134a: the six farmers'), whose ``Move end1`` W19 leaves as his, so
    its chain point moves with the speed slider, not as :meth:`Swing.ticks`
    times it: its damage per second is his, measured at speed 1 alone."""

    def pace(self, speed: float = 1.0) -> float | None:
        """The basics' mean chain point in ticks at ``speed`` (> 0), each
        where W19 puts it (:meth:`Swing.ticks`); ``None`` when none hits."""
        ticks = [s.ticks(speed)[1] for col in self.basics for s in col if s is not None]
        return statistics.fmean(ticks) if ticks else None

    def rate(self, speed: float = 1.0) -> float | None:
        """The body's :func:`combo_rate` at ``speed`` (> 0) and the damage
        slider's 1; ``None`` when a basic or both finishers hit nothing."""
        def term(swings: tuple[Swing | None, ...]) -> tuple[float, ...] | None:
            if not swings or None in swings:
                return None
            return tuple(statistics.fmean(v) for v in zip(*((s.multiplier, *s.ticks(speed)) for s in swings)))
        basics = [term(col) for col in self.basics]
        ends = [t for col in self.finishers if (t := term(col)) is not None]
        if None in basics or not ends:
            return None
        return combo_rate(basics, (statistics.fmean(m for m, _, _ in ends), statistics.fmean(h for _, h, _ in ends)))


def weigh_attacks(characters_xbr: bytes, body: Body, scale: float, vanilla, anims,
                  picks: list[str], x3: int, rotate: tuple[list[int], int] | None,
                  exact: bool = False, reach: float = 1.0,
                  fill: int = 0, borrowed: int = 0,
                  given: dict[str, tuple[DamageWindow, ...]] | None = None, held: Loadout | None = None,
                  balance: bool = True, x3_far: float | None = None, model_scale: float = 1.0
                  ) -> tuple[list[float | None], int, list[list[float | None]], tuple[float, bool] | None,
                             Combo | None]:
    """The attack balance (D223, D228) of a build on ``body`` at ``scale``:
    each ``attacks_anims`` column's B (:func:`balance_factor`; ``None`` for
    the roll and a column no hit can be weighed for), the columns whose
    reach X13 bumps (a mask), for each entry of X10's ring the B of
    its clip in each column that rotates (``None`` elsewhere): a rotating
    swing plays the entry's clip at the entry's Rate in its own column's
    move, against garret4's attack for that column; and the factor
    its every held B is multiplied by, with whether the body is a slow
    attacker (:data:`SLOW_RATIO`), or ``None`` for none (garret4's
    exact, whose moves are his, and a body whose one-target
    :func:`combo_rate` is garret4's or more): the one that makes its
    combo_rate :data:`SLOW_BONUS` times garret4's on a slow attacker
    (D350, Step 2.132; AZ-614; :data:`SLOW_BONUS` itself where a basic
    or both finishers hit nothing), garret4's on any other body (D389),
    never under 1.0, each product held to at most :data:`BALANCE_CAP`
    times that aim (5.0, 4.0).  The chain ticks (garret4's own in a
    column of ``borrowed``) read W19's contact with the target ahead, the boxes ``reach`` times as X13
    grows them (x :data:`REACH_BUMP` in a bumped column) and filled in
    the columns of ``fill`` (:func:`fill_mask`).  ``vanilla`` is the
    vanilla table (garret4's clip and Rate per column: the norm, at scale
    1), ``anims`` the build's (its Rate after W5, before the speed
    slider), ``picks`` the clips W3 gave (:func:`substitutes`), ``x3`` X3's
    columns (its box reaching ``x3_far`` where the build puts it, at the
    action point or a prop's tip, AZ-415; ``None``, garret4's attack_1 box
    where he holds it, at :data:`X3_OPENS`-:data:`X3_CLOSES`
    of the move; with ``exact``, garret4's exact, garret4's own move, which
    W5 plays in his time, with X3's window and box for it,
    :func:`garret4_window`, Step 2.68: 1 but where it joins his windows;
    so too each column of ``borrowed``, :attr:`Loadout.borrowing`, Step 2.134a;
    X3's window on an attack style's clip, :func:`style_windows`,
    ``given``, Step 2.159a; with ``held``, the build's :class:`Loadout`, X3's window grown to its
    carried prop's tip drawn ``scale`` times, :func:`held_window`, W26, Step 2.134b) and
    ``rotate`` X10's ring (:func:`rotation`).  The bump
    goes to a melee column whose box reaches less than :data:`BUMP_BELOW`
    of garret4's basic1 reach (a column X10 turns only when every clip its
    ring plays does; never an X3 column, whose box is garret4's), both
    judged at the build's Model size 1, its boxes over ``model_scale`` as
    the logic's melee line (:func:`melee_reach`, AZ-559; AZ-567).  Last
    the :class:`Combo` its multipliers and chain ticks make (Step 2.165b,
    D358's match; ``None`` in garret4's exact); with ``balance`` false, a
    build that weighs nothing, its B ``None`` throughout, no bump, no
    factor and the combo garret4's multipliers.  Every B, after the
    factor, is held on garret4's side of the game's heavy-hit line
    (:func:`heavy_side`, D799, AZ-774)."""
    garret4 = read_body(characters_xbr, PLAYER)
    columns = anims.col_names()
    given = given or {}
    prop_lo = held   # the Loadout (``held`` names the B list below)
    boxes: dict[tuple[str, str, float], tuple[DamageWindow, ...]] = {}

    def windows(name: str, clip: str, at: float = 1.0) -> tuple[DamageWindow, ...]:
        if (name, clip, at) not in boxes:
            boxes[name, clip, at] = damage_windows(characters_xbr, name, clip, at)
        return boxes[name, clip, at]
    norm_clips = [vanilla.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]
    sent: dict[int, tuple[DamageWindow, ...]] = {}

    def norm_windows(i: int) -> tuple[DamageWindow, ...]:
        """garret4's boxes for column ``i``'s move, the norm, as the game
        sends them (AZ-804, Step 2.202b: back by his clip's ``m_feet``,
        :func:`sent_windows`, as a borrowed column's since Step 2.197b's
        F1); his clip's own in garret4's exact, whose X3 boxes are his
        clip's too."""
        if exact and not borrowed >> i & 1:
            return windows(PLAYER, norm_clips[i])
        if i not in sent:
            sent[i] = sent_windows(characters_xbr, PLAYER, norm_clips[i],
                                   vanilla.find_cell(columns[i], "Rate", i).double_value)
        return sent[i]
    x3_reach = max(w.reach for w in windows(PLAYER, "attack_1")) if x3_far is None else x3_far
    basic = norm_clips[columns.index("basic1")]
    below = BUMP_BELOW * max((w.reach for w in windows(PLAYER, basic)), default=0.0)

    def short(clip: str) -> bool:
        owner, played = source_clip(body, garret4, clip)
        own = windows(owner.name, played, scale)
        return bool(own) and is_melee(own, model_scale) and max(w.reach for w in own) < below * abs(model_scale)
    ring, turns = rotate or ([], 0)
    ring_short = bool(ring) and all(short(picks[i]) for i in ring)
    bump = sum(1 << i for i, (col, pick) in enumerate(zip(columns, picks)) if col != ROLL
               and not x3 >> i & 1 and (ring_short if turns >> i & 1 else short(pick))) if balance else 0
    rates = [anims.find_cell(col, "Rate", i).double_value for i, col in enumerate(columns)]
    norms: dict[int, AttackMove | None] = {}

    def moves(i: int, clip: str, rate: float) -> tuple[AttackMove | None, AttackMove | None]:
        """garret4's move for column ``i`` and ``clip``'s played at ``rate`` in it."""
        if columns[i] == ROLL or norm_clips[i] not in garret4.clips:
            return None, None
        window = move_window(anims, i)
        norm_rate, norm_length = vanilla.find_cell(columns[i], "Rate", i).double_value, garret4.length(norm_clips[i])
        if i not in norms:   # his move as the game sends it (AZ-804)
            norms[i] = attack_move(norm_rate, norm_length, window, norm_windows(i))
        if (exact or borrowed >> i & 1) and x3 >> i & 1:   # garret4's move (W5) with X3's box for it (Step 2.68)
            box = (held_window(characters_xbr, norm_clips[i], scale, prop_lo) if prop_lo
                   else garret4_window(characters_xbr, garret4, norm_clips[i]))
            if box is not None and borrowed >> i & 1:   # AZ-766: his attack baked on the rig, its box as the game
                box = sent_window(characters_xbr, PLAYER, norm_clips[i], norm_rate, box)   # sends it (the review's F1)
            return norms[i], attack_move(norm_rate, norm_length, window, (box,) if box else ())
        owner, own = source_clip(body, garret4, clip)
        return norms[i], attack_move(rate, owner.length(own), window,
                                     given.get(clip) if x3 >> i & 1 else windows(owner.name, own, scale), x3_reach)

    def weigh(i: int, clip: str, rate: float) -> float | None:
        """B of ``clip`` played at ``rate`` in column ``i``'s move."""
        return balance_factor(*moves(i, clip, rate), REACH_BUMP if bump >> i & 1 else 1.0)
    held = [weigh(i, pick, rates[i]) if balance else None for i, pick in enumerate(picks)]
    entries = [[weigh(c, picks[h], rates[h]) if balance and turns >> c & 1 else None for c in range(len(columns))]
               for h in ring]
    base = [c.double_value if (c := vanilla.find_cell(col, MULTIPLIER, i)) is not None and c.type_code == 1
            else 1.0 for i, col in enumerate(columns)]

    def sided(bs: list[float | None]) -> list[float | None]:
        """Each column's B on garret4's side of the heavy-hit line (D799, :func:`heavy_side`)."""
        return [heavy_side(b, m) for b, m in zip(bs, base)]
    if exact:
        return sided(held), bump, [sided(row) for row in entries], None, None

    timed: dict[tuple[int, int], tuple[tuple[float, float] | None, tuple[float, float] | None]] = {}
    parts: dict[tuple[int, int], tuple] = {}   # chain_ticks' arguments for the body's (i, h): its Swing

    def ticks(i: int, h: int) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
        """garret4's (first hit, chain) ticks in column ``i`` (his first
        hit + 0.2 s) and the body's playing ``picks[h]`` at ``rates[h]``
        in it (W19's, from its contact with the target ahead)."""
        if (i, h) in timed:
            return timed[i, h]
        if columns[i] == ROLL or norm_clips[i] not in garret4.clips:
            return None, None
        window = move_window(anims, i)
        his = (vanilla.find_cell(columns[i], "Rate", i).double_value, garret4.length(norm_clips[i]),
               window, windows(PLAYER, norm_clips[i]))
        norm = chain_ticks(*his)
        if borrowed >> i & 1 and h == i:   # garret4's own move, box and chain (Step 2.134a)
            timed[i, h], parts[i, h] = (norm, norm), (*his, None)
            return timed[i, h]
        owner, own = source_clip(body, garret4, picks[h])
        met = None if x3 >> i & 1 else contact(characters_xbr, owner.name, own, scale, owner.length(own), window,
                                               reach * (REACH_BUMP if bump >> i & 1 else 1.0), bool(fill >> i & 1))
        parts[i, h] = (rates[h], owner.length(own), window,
                       given.get(picks[h]) if x3 >> i & 1 else windows(owner.name, own, scale), met)
        timed[i, h] = norm, chain_ticks(*parts[i, h])
        return timed[i, h]

    def played(i: int) -> list[int]:
        return ring if turns >> i & 1 else [i]
    paces = [(n[1], m[1]) for i, col in enumerate(columns) if col in CHAINED
             for n, m in (ticks(i, h) for h in played(i)) if n and m]
    slow = bool(paces) and (statistics.fmean(m for _, m in paces)
                            >= SLOW_RATIO * statistics.fmean(n for n, _ in paces))

    def term(col: str, own: bool) -> tuple[float, float, float] | None:
        """(multiplier, first hit tick, chain tick) column ``col`` deals one
        target, garret4's or the body's (its ring entries' mean)."""
        i = columns.index(col)
        rows = []
        for h in played(i) if own else [i]:
            norm, move = ticks(i, h)
            t = move if own else norm
            if t is None:
                return None
            b = (entries[ring.index(h)][i] if turns >> i & 1 else held[i]) if own else 1.0
            rows.append((base[i] * (1.0 if b is None else b), *t))
        return tuple(statistics.fmean(v) for v in zip(*rows))

    def rate(own: bool) -> float | None:
        basics = [term(col, own) for col in CHAINED]
        ends = [t for col in FINISHERS if (t := term(col, own)) is not None]
        if None in basics or not ends:
            return None
        return combo_rate(basics, (statistics.fmean(m for m, _, _ in ends), statistics.fmean(h for _, h, _ in ends)))
    norm_rate, own_rate = rate(False), rate(True)
    aim = SLOW_BONUS if slow else 1.0   # D350; D389: never under garret4's
    k = max(1.0, aim * norm_rate / own_rate) if norm_rate and own_rate else aim
    lift = None if k == 1.0 and not slow or not balance else (k, slow)
    if lift is not None:
        top = BALANCE_CAP * aim
        held = [None if b is None else min(b * k, top) for b in held]
        entries = [[None if b is None else min(b * k, top) for b in row] for row in entries]
    held, entries = sided(held), [sided(row) for row in entries]   # D799, last: the lift's evening on its side

    def swings(col: str) -> tuple[Swing | None, ...]:
        """Column ``col``'s swings as the build writes them (Step 2.165b)."""
        i, out = columns.index(col), []
        for h in played(i):
            if ticks(i, h)[1] is None:
                out.append(None)
                continue
            b = entries[ring.index(h)][i] if turns >> i & 1 else held[i]
            r, clip, window, hits, met = parts[i, h]
            hit, touch, _ = _chain_at(r, clip, window, hits, met)
            kept = None
            if not (turns | borrowed) >> i & 1:   # W19's column: its Move end1 as chain_point reads it
                a0, a1, e1 = (c.double_value if (c := anims.find_cell(col, row, i)) is not None
                              and c.type_code == 1 else None for row in ("Anim start", "Anim end", "Move end1"))
                if None not in (a0, a1, e1) and a1 != a0:
                    kept = ((e1 - a0) / (a1 - a0) - window[0]) * clip / r
            out.append(Swing(base[i] * (1.0 if b is None else b), hit, touch, (window[1] - window[0]) * clip / r,
                             kept, met is not None))
        return tuple(out)
    combo = Combo(statistics.fmean(n for n, _ in paces) if paces else None, norm_rate,
                  tuple(swings(col) for col in CHAINED), tuple(swings(col) for col in FINISHERS),
                  any(borrowed >> columns.index(col) & 1 for col in CHAINED))
    return held, bump, entries, lift, combo


CASTS = ("elemental1", "elemental2", "elemental3")
"""The ``attacks_anims`` columns of the staff's elemental casts: magic,
so the logic's melee reach (:func:`melee_reach`) never counts them as
the basic swing D237 asks for (AZ-559)."""

IDLE_SWINGS = ("basic1", "sweep1", "sweep2")
"""The ``attacks_anims`` columns a press from idle plays: basic1 and the
sweeps the attack search turns it into (sweep1 for basic1, sweep2 for
basic2 with the stick held, the first of a set; Step 2.135's search),
the only ones the logic's melee reach reads (AZ-566, D719): basic2, the
finishers and the directional swings chain onto a hit or a stunned
target, so from idle the player meets a switch or a barrier with none of
them."""


@dataclass
class AttackLogic:
    """What the randomizer's logic reads of a swapped body's attacks, as
    :func:`apply_player_model` builds them (Step 2.73;
    :func:`azurkit.tools.randomizer.layer.movement_reasons`): ``reach``, the
    farthest a melee box of the swings a press from idle plays
    (:data:`IDLE_SWINGS`, AZ-566) reaches straight ahead of the feet
    (m, :func:`melee_reach` at the model scale by each box's forward
    extent, Step 2.137, AZ-604; ``None`` when none of them is melee; since
    D726 the logic flags only that and 0.0, no box ahead of the feet, never
    a length; D358's match-Garret reach reads the number);
    ``damage``, the least damage an attack deals as a share of garret4's
    for it (B x the damage slider, :func:`weigh_attacks`, B 1.0 without
    the balance; on a body with no clips and on garret4's own, the
    slider: Step 2.123); ``speed``, the speed slider, which the logic
    reads only at 0 or less, where no attack ends (D247; Step 2.123's
    default for its F4)."""

    reach: float | None = None
    damage: float = 1.0
    speed: float = 1.0
    size: float = 1.0
    """The body's size s (:func:`body_size`, Step 2.133): randomize-full
    folds it into the walk and roll sliders before its plan and checks
    it against this, the build's own."""
    height: float | None = None
    """The body's height drawn at Model size 1 in metres, its mesh's top
    (:func:`~azurik_mod.assets.characters.height`) at its size's scale:
    D358's match-Garret Model size stands it at garret4's 2.002 m (Step
    2.165b; ``None`` on garret4's own body)."""
    combo: Combo | None = None
    """Its combo on one target as W14 times it (:class:`Combo`; Step
    2.165b, D358's match-Garret attack speed and damage): own mode's body
    with clips, balanced or not; ``None`` where garret4's attack timing
    plays (Skin only, a body with no clips, garret4's own)."""


def melee_reach(characters_xbr: bytes, body: Body, columns: list[str], picks: list[str], scale: float,
                x3: int, x3_far: float, rotate: tuple[list[int], int] | None = None,
                exact: list[str] | None = None, reach: float = 1.0, bump: int = 0,
                only: tuple[str, ...] | None = None, melee: bool = True,
                model_scale: float = 1.0, ahead: bool = False, held: Loadout | None = None,
                rates: list[float] | None = None) -> float | None:
    """The farthest a melee box (:func:`is_melee` at ``model_scale``, the
    size the build draws the body times its size's, AZ-559; any box when
    ``melee`` is false) of a build's attacks reaches from the feet, in
    metres (Step 2.73), to its farthest corner, or with ``ahead`` straight
    ahead (:attr:`~azurik_mod.assets.characters.DamageWindow.forward`, the
    logic's: Step 2.137, AZ-604; ``x3_far`` then X3's box's forward
    extent), the melee line still each box's corner, over every column
    but the roll and, for a melee
    box, the staff's casts (:data:`CASTS`, magic) (``only``: those
    columns alone):
    X3's box in a column of ``x3`` (garret4's own for its
    vanilla clip, ``exact[i]``, in garret4's exact, if that is melee at
    his size, which X3 keeps; else garret4's box, melee, at
    ``x3_far``, where the build put it,
    :func:`~azurik_mod.patches._player_damage_marker.x3_reach`, or on a
    hand, which no build measures, garret4's basic swing,
    :data:`~azurik_mod.patches._player_damage_marker.GARRET4_REACH`:
    D237), else the clips it plays on
    ``body`` at ``scale`` (``picks``; a column X10 turns, every clip of
    ``rotate``'s ring), times X13's ``reach`` and :data:`REACH_BUMP` in a
    column of ``bump``, at least 0.0; ``None`` when no box is melee.
    With ``held`` (the build's :class:`Loadout`; W26, Step 2.134b) an ``exact`` column's box is grown to
    its carried prop's tip drawn ``scale`` times (:func:`held_window`), its
    class still garret4's own box's: his unscaled box is in every grown
    one, so judged by its own corner a grown box would leave the melee
    line at x2 and x0.5.  With ``rates`` (each column's Rate) each box is
    read from the body as the game sends it (:func:`sent_window`, AZ-766,
    Step 2.197b: a lunge's back by its clip's horizontal ``m_feet`` at each
    tick, seen to the millimetre on garret4's own staff), the logic's."""
    garret4 = read_body(characters_xbr, PLAYER)
    seen: dict[tuple[str, int], tuple[DamageWindow, ...]] = {}

    def sent(owner: str, clip: str, h: int, w: DamageWindow | None) -> DamageWindow | None:
        return w if w is None or rates is None else sent_window(characters_xbr, owner, clip, rates[h], w)

    def his(i: int, w: DamageWindow | None) -> DamageWindow | None:   # X3's box for his clip, sent from the body
        # where that clip plays (borrowed onto the rig, his own body); another clip's (garret4's exact on another
        # body) or a floating prop's root carrier (keyed back by his m_feet) as built
        owner, own = source_clip(body, garret4, picks[i]) if picks else (body, "")
        if owner.name != PLAYER or own != exact[i] or held is not None and held.carry == FLOAT:
            return w
        return sent(PLAYER, own, i, w)

    def windows(clip: str, h: int) -> tuple[DamageWindow, ...]:
        if (clip, h) not in seen:
            owner, own = source_clip(body, garret4, clip)
            seen[clip, h] = (damage_windows(characters_xbr, owner.name, own, scale) if rates is None
                             else sent_windows(characters_xbr, owner.name, own, rates[h], scale))
        return seen[clip, h]
    ring, turns = rotate or ([], 0)
    hits = []
    for i, col in enumerate(columns):
        if col == ROLL or melee and col in CASTS or only is not None and col not in only:
            continue
        if x3 >> i & 1 and not exact:
            far = [x3_far]
        else:
            if x3 >> i & 1:
                box = his(i, garret4_window(characters_xbr, garret4, exact[i]))
                boxes, at = [(box,) if box else ()], 1.0
                grown = [(his(i, held_window(characters_xbr, exact[i], scale, held)),) if box else ()] if held else boxes
            else:
                boxes = [windows(picks[h], h) for h in ring] if turns >> i & 1 else [windows(picks[i], i)]
                at, grown = model_scale, boxes
            far = [max(w.forward if ahead else w.reach for w in gs) for ws, gs in zip(boxes, grown)
                   if ws and (is_melee(ws, at) or not melee)]
        hits += [f * reach * (REACH_BUMP if bump >> i & 1 else 1.0) for f in far]
    return max(*hits, 0.0) if hits else None


TICK_EDGE = 1e-5
"""How near (clip s) a tick may fall outside a window's edge and still
count as in it (:func:`sent_window`): X3's rows hold the edges as float32
fractions, and sweep1's window opens on a tick (0.4 s), where the game
sends its first box."""


def sent_window(characters_xbr: bytes, owner: str, clip: str, rate: float, w: DamageWindow) -> DamageWindow:
    """X3's box ``w`` for ``owner``'s ``clip`` (metres from the feet in
    the clip's frame) as the game sends it (AZ-766, Step 2.198): at each
    tick whose clip time falls in its window (``rate`` clip seconds a
    1/30 s tick from the clip's start) the damage pass places it from the
    drawn origin, which the game keeps back from the body by the clip's
    horizontal ``m_feet`` there, so a lunge's box stands that much nearer
    the body: the bounds of those boxes, its reach their farthest corner
    and its near the nearest one's.  Step 2.195b's record read each such
    column to the millimetre (its sitting's record, R2: basic2's attack_9 0.425 and 0.481 m back at its
    two ticks, basic3's attack_3 0.376 at its first, sweep1's 0.86, the
    finish's attack_10 0.84, where it holds its ``m_feet`` still); ``w``
    itself where ``m_feet`` stays at the origin."""
    at = next((i for i, m in enumerate(read_body(characters_xbr, owner).markers) if m.casefold() == ROOT_NODE), -1)
    lead = {tr.comp: tr.keys for tr in named_clip(characters_xbr, owner, clip).markers
            if tr.target == at and tr.comp in (0, 1)}
    step = rate / 30.0 if rate > 0 else 0.0
    ticks = [n * step for n in range(math.floor((w.off + TICK_EDGE) / step) + 1) if n * step >= w.on - TICK_EDGE] \
        if step else []
    backs = [[evaluate(lead[c], t) if c in lead else 0.0 for c in (0, 1)] for t in ticks or [w.on]]
    if not any(any(back) for back in backs):
        return w
    boxes = [((w.low[0] - x, w.low[1] - y, w.low[2]), (w.high[0] - x, w.high[1] - y, w.high[2])) for x, y in backs]
    low = tuple(min(b[0][c] for b in boxes) for c in range(3))
    high = tuple(max(b[1][c] for b in boxes) for c in range(3))
    return DamageWindow(w.marker, w.on, w.off, low, high,
                        max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1])),
                        min(near(*b) for b in boxes))


def sent_windows(characters_xbr: bytes, owner: str, clip: str, rate: float,
                 scale: float = 1.0) -> tuple[DamageWindow, ...]:
    """``owner``'s own ``clip``'s damage windows at ``scale``
    (:func:`~azurik_mod.assets.characters.damage_windows`) as the game
    sends them (AZ-766, Step 2.197b): each box its marker builds at a tick
    in the window (``rate`` clip seconds a 1/30 s tick from the clip's
    start) back by the clip's horizontal ``m_feet`` there, from the drawn
    origin the game keeps that far behind the body (:func:`sent_window`'s
    rule, per tick: sitting 2.197b's G4V row read garret4's own staff's
    every box so, basic2, basic3, the finish and sweep2, to the
    millimetre); the windows themselves where ``m_feet`` stays at the
    origin."""
    windows = damage_windows(characters_xbr, owner, clip, scale)
    at = next((i for i, m in enumerate(read_body(characters_xbr, owner).markers) if m.casefold() == ROOT_NODE), -1)
    lead = {tr.comp: tr.keys for tr in named_clip(characters_xbr, owner, clip).markers
            if tr.target == at and tr.comp in (0, 1)} if windows and at >= 0 else {}
    step = rate / 30.0 if rate > 0 else 0.0
    if not lead or not step:
        return windows
    boxes = damage_boxes(characters_xbr, owner, clip, scale)
    out = []
    for w in windows:
        mine = [(t, lo, hi) for name, t, lo, hi in boxes if name == w.marker and w.on - TICK_EDGE <= t <= w.off + TICK_EDGE]
        ticks = [n * step for n in range(math.floor((w.off + TICK_EDGE) / step) + 1) if n * step >= w.on - TICK_EDGE]
        sent = []
        for t in ticks or [w.on]:
            _, lo, hi = min(mine, key=lambda b: abs(b[0] - t))
            x, y = (evaluate(lead[c], t) if c in lead else 0.0 for c in (0, 1))
            sent.append(((lo[0] - x, lo[1] - y, lo[2]), (hi[0] - x, hi[1] - y, hi[2])))
        low = tuple(min(b[0][c] for b in sent) for c in range(3))
        high = tuple(max(b[1][c] for b in sent) for c in range(3))
        out.append(DamageWindow(w.marker, w.on, w.off, low, high,
                                max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1])),
                                min(near(*b) for b in sent)))
    return tuple(out)


@dataclass(frozen=True)
class Attack:
    """One ``attacks_anims`` column as a player model plays it: the clip
    W3 gives it (W17's copy as the clip it copies), that clip's length (s)
    and damage windows at the model's scale, whether X3's marker hits for
    it instead (garret4's
    attack_1 box, 20-50% of each attack move; in garret4's exact his own
    box and window for the column, Step 2.68), whether X3's box is
    garret4's where he holds it, not at the action point
    (:func:`x3_anchor`, Step 2.70b), and whether X13's fill would fill
    its box (every attack column but the roll, Step 2.132; garret4's own
    body only drawn at a Model size other than 1)."""

    column: str
    clip: str
    length: float
    windows: tuple[DamageWindow, ...]
    x3: bool
    ground: bool
    x3_feet: bool = False
    styled: bool = False
    """An attack style's clip (the bare-hands kit, :attr:`Loadout.kit`): ``windows`` its X3 window."""
    borrowed: bool = False
    """garret4's own attack for the column baked onto the rig (:attr:`Loadout.borrowing`, Step 2.134a):
    ``windows`` the box and window X3 installs for it, his own (:func:`garret4_window`), or with ``held``
    grown to the carried prop's tip (:func:`held_window`, W26)."""
    held: bool = False
    tipped: bool = False
    """X3's box at a rigid prop's tip in place of the body's own (:attr:`Loadout.tip`, Step 2.161e): ``windows``
    the body's own, whose span X3's row takes (none: X3's 20-50% of the move)."""
    boxed: str = ""
    """X3's box the style's own (:func:`style_windows`: the kit's at the limb its clip strikes with, Step 2.195;
    Balthazar's own, Step 2.195b), in the listing's words, ``windows`` its window and box; else empty."""


def attacks(config_xbr: bytes, characters_xbr: bytes, species: str,
            mode: str = DEFAULT_MODE, size: str = DEFAULT_SIZE, model_scale: float = 1.0,
            weapon: str | None = None) -> list[Attack]:
    """Every ``attacks_anims`` column of a ``species`` build in gameplay
    ``mode`` (:data:`MODES`) and ``size`` (:data:`SIZES`) drawn
    ``model_scale`` times that size (Step 2.98), at the scale it builds,
    in table order (:func:`substitutes`, :func:`x3_mask` with
    own mode's reach test and X10 ring, :func:`hitting_ring`,
    :func:`fill_mask`; garret4's exact, no X10, Step 2.68);
    garret4's build writes no Anim, so it plays the table's own, and X13
    fills them only drawn at a ``model_scale`` other than 1.  On a body the mode's rule bakes for
    (:func:`bakes`, B) the roll plays garret4's ``roll_forward`` baked
    onto it, in his length (:func:`source_clip`), and in garret4's exact
    seven or eight attack columns his own clips (:func:`substitutes`);
    a pick W3's plan moves (:func:`place_anims`: spideyzar's whirlwind
    into finish) where the build plays it (Step 2.135);
    a column W17 gives a copy (Step 2.75e) lists the clip it copies;
    garret4 drawn at ``model_scale`` plays his own boxes that many times
    their size (Step 2.123).  The body's weapon is the build's
    (:func:`loadout`, Step 2.161a): a column that swings garret4's own
    attack lists the box and window X3 installs for it (Step 2.134a), grown
    to a carried prop's tip (W26), as the game sends it (:func:`sent_window`,
    AZ-766: a lunge's from the body at each tick); ``weapon`` the one picked (Step
    2.161b: a copied prop's tip where the wearer's own hand carries it;
    Step 2.161e: on a creature or token, X3's box at a rigid prop's tip).
    The recipe the build plays (AZ-763, Step 2.198): a moveset weapon's
    (booblord spin's spins, :attr:`Loadout.recipe`) or own mode's W23
    overlay (the air elemental's gust) gives its columns its own clips
    (``v/``), generated on the body as W22 makes them, each listed with
    its own boxes and, as X13 leaves them, no fill.
    ``[]`` for a body with no clips.
    :class:`ValueError` names why the species can't be used."""
    from azurkit.tools.characters import _player_variants as variants
    doc = XbrDocument.from_bytes(config_xbr)
    rows = _species(doc.keyed_section("critters_engine"))
    why = _refusal(rows, body_names(characters_xbr), species)
    if why:
        raise ValueError(f"{species!r}: {why}")
    body = read_body(characters_xbr, rows[species]["body"])
    if not body.clips:
        return []
    anims = doc.keyed_section("attacks_anims")
    columns = anims.col_names()
    himself = species == PLAYER
    clips = [anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]
    exact = mode == "garret4"
    baked = bakes(body, MODE_ANIMS[mode])
    lo = loadout(characters_xbr, body, mode, baked, None, weapon)   # the build's weapon (Step 2.161a): _dress's
    style, borrowing = lo.kit, lo.borrowing
    vanilla = himself and style is None   # his own attacks (Step 2.161d: a style on his rig is a swap's)
    held = lo.reaching or lo.carry == ON_CHAIN   # X3's rows grown to a carried prop's tip (W26; his hoe)
    picks = clips if himself else substitutes(columns, body, baked,
                                              anim_strings(anims) if baked and exact or borrowing else None,
                                              floats=floats(species, mode, baked), borrow=borrowing)
    if style is not None:
        picks = style_picks(style, columns, picks)
    # AZ-763 (Step 2.198): the recipe the build plays (_dress's ``worn``): a moveset weapon's laid over the body
    # (booblord spin's), else in own mode W23's own-build overlay; its columns play its clips (W22's v/)
    worn = (lo.recipe if lo.recipe is not None else variants.overlay(species) if mode == "own" and not lo.picked
            else None)
    if worn is not None and worn.columns:
        why = variants.refusal(worn, rows, columns, body)
        if why:
            raise ValueError(f"{species!r}: {why}")
        picks = [worn.clip_of(col) or pick for col, pick in zip(columns, picks)]
    scale = ((size == "garret4" and size_scale(characters_xbr, body))
             or (1.0 if mode == "garret4" else rows[species]["scale"] or 1.0)) * model_scale
    if not himself and not borrowing:   # W3's plan may move a pick (spideyzar's whirlwind), as the build plays it
        copies = {clip: name for clip, (name, _) in attack_copies(characters_xbr, body, picks, mode, scale).items()}
        named = [copies.get(pick, pick) for pick in picks]
        place_anims(columns, anim_strings(anims), named)
        plain = {name: clip for clip, name in copies.items()}
        picks = [plain.get(pick, pick) for pick in named]
    if worn is not None and worn.columns:   # W22 on a scratch copy: its clips generated on the body, so each
        # column lists its clip's own boxes (its markers the body lacks grown; its fx, which no box reads, left out)
        have = {m.casefold() for m in body.markers}
        characters_xbr, _ = variants.grow(characters_xbr, None, body, replace(
            worn, markers=tuple(m for m in worn.markers if m.casefold() not in have), fx=(), fx_grafts=(),
            fx_ring=None))
        body = variants.reread(characters_xbr, body)
    garret4 = read_body(characters_xbr, PLAYER)
    given = style_windows(style, picks, characters_xbr, body, scale) if style is not None else {}
    limbed = bool(given)   # Step 2.195: the style's own boxes, X3 anchored at the feet
    boxed = (f"{style.source}'s own box for the clip" if style is not None and style.own is not None
             else "the kit's box at its fist or foot")   # Step 2.195b: Balthazar's blast and beam
    rotate = None if vanilla or exact or worn is not None and not worn.rotate else rotation(columns, picks, body)
    if mode == "own" and rotate:
        rotate = hitting_ring(characters_xbr, body, picks, scale, rotate)
    x3 = ((1 << len(columns)) - 1 if held else 0) if vanilla else x3_mask(mode, columns, picks, body, reach_misses(
        characters_xbr, body, columns, picks, scale, rotate) if mode == "own" else 0)
    ground = fill_mask(columns) if not vanilla or model_scale != 1.0 else 0   # a style on his rig: the swap's
    if worn is not None:   # a recipe's own clips keep their boxes as keyed (Step 2.137); a moveset brings its rule
        ground = (0 if lo.lent and worn.ground is False else ground) & ~variants.authored(worn, columns)
    feet = bool(x3) and not exact and not borrowing and not held and (limbed or x3_anchor(
        characters_xbr, body, action_point(characters_xbr, body, picks), anims, picks, x3, scale, rotate,
        x3_side(model_scale))[2] == GARRET4_BOX)
    out = []
    for i, (col, pick) in enumerate(zip(columns, picks)):
        if style is not None and pick.startswith(style.dir):   # a style's clip on its rig: its length, X3's box
            # in its window (Step 2.159a), X3's own on a clip without one
            out.append(Attack(col, pick, style.lengths[pick[len(style.dir):]], given.get(pick, ()), bool(x3 >> i & 1),
                              bool(ground >> i & 1), feet, styled=True, boxed=boxed if pick in given else ""))
            continue
        owner, clip = source_clip(body, garret4, pick)
        if (borrowing or vanilla and held) and col != ROLL:   # garret4's own box and window for the column, grown
            # to a carried prop's tip: X3's row as the build installs it (Step 2.134a; W26; his hoe, Step 2.161d)
            box = (held_window(characters_xbr, clip, scale, lo) if held
                   else garret4_window(characters_xbr, garret4, clip))
            if box is not None:   # AZ-766: as the game sends it, from the body at each tick (his Rate: W5's)
                box = sent_window(characters_xbr, owner.name, clip, anims.find_cell(col, "Rate", i).double_value, box)
            out.append(Attack(col, pick, owner.length(clip), (box,) if box else (), bool(x3 >> i & 1),
                              bool(ground >> i & 1), feet, borrowed=True, held=held))
            continue
        rate = c.double_value if (c := anims.find_cell(col, "Rate", i)) is not None and c.type_code == 1 else 0.0
        windows = sent_windows(characters_xbr, owner.name, clip, rate, scale)   # Step 2.197b: from the body (AZ-766)
        tipped = lo.tip and col != ROLL   # Step 2.161e: X3 at its rigid prop's tip, in its own clip's windows
        out.append(Attack(col, pick, owner.length(clip), windows, (bool(x3 >> i & 1) or tipped) and col != ROLL,
                          bool(ground >> i & 1), feet and not tipped, tipped=tipped))
    return out


# --- X16: the air armor's wings flap (Step 2.77) ----------------------------
WINGS_MARKER = "m_jump"
"""The body marker the air armor's fx (fx_jump1-3) binds the restart of its
wing timer to; garret4's superjump pulses it on each flap. Only garret4's
body has one."""
WINGS_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="wings")
WINGS_SHIM_NAME = "player_model_wings"
"""Its object's name: ``player_model_wings.o`` in the shim build dir."""
ARMOR_NODES = {
    "m_root": "root_joint", "m_chest": "spine_2", "m_waist": "spine_2", "m_skull": "head",
    "m_shoulderLeft": "left_arm_1", "m_shoulderRight": "right_arm_1",
    "m_wristLeft": "left_arm_2", "m_wristRight": "right_arm_2",
    "m_ankleLeft": "left_leg_2", "m_ankleRight": "right_leg_2",
}
"""The ten garret4 nodes the armors' fx bind their pieces to, each with
the bone of his that carries it (his marker a constant offset from it over
his 95 clips: AZ-447's read). On a swapped body X16 binds each to a bone
of the body (Step 2.118, D294)."""
ARMOR_NEAR = 0.10
"""How near a piece's point, as a fraction of the body's height, a bone
must be to carry it on a body the role map doesn't serve."""
ARMOR_ENTRY = 84
"""One armor table entry: the name (16 bytes), the bone (i32), C (16 f32)."""
WINGS_ARMOR = BytesParam(
    name="armor", symbol="_player_model_wings_armor", size=4 + len(ARMOR_NODES) * ARMOR_ENTRY,
    label="Player model armor binds (X16)")
"""X16's armor table (:func:`armor_table`), in both hooks' landings."""
WINGS_GROWN = BytesParam(
    name="grown", symbol="_player_model_wings_grown", size=64,
    label="Player model: the body W27 grew m_root on (X16)")
"""The body W27 grew ``m_root`` on (its name, NUL-ended; empty: none), in
both hooks' landings: another critter wearing it (an NPC) binds no
``m_root`` (Step 2.134b)."""
WINGS_BIND = TrampolinePatch(
    name="player_model_wings_bind",
    label="Player model wings: a virtual m_jump (X16) at VA 0x44355",
    va=0x44355,   # the bind interface's slot 1 (0x44270)
    replaced_bytes=bytes.fromhex("e8765e0800"),    # CALL 0xCA1D0
    shim_object=WINGS_SHIM.object_path(WINGS_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_wings_bind",
    bytes_params=(WINGS_ARMOR, WINGS_GROWN),
)
WINGS_POSE = TrampolinePatch(
    name="player_model_wings_pose",
    label="Player model wings: m_jump pulses on each flap (X16) at VA 0x44389",
    va=0x44389,   # the bind interface's slot 2 (0x44370)
    replaced_bytes=bytes.fromhex("e8628a0800"),    # CALL 0xCCDF0
    shim_object=WINGS_SHIM.object_path(WINGS_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_wings_pose",
    bytes_params=(WINGS_ARMOR, WINGS_GROWN),
)


def needs_wings_shim(body: Body) -> bool:
    """Whether ``body`` needs X16: it has no :data:`WINGS_MARKER`, so the
    air armor's wings never restart their stroke on a flap."""
    return WINGS_MARKER not in body.markers


def _armor_frames(fx_raw) -> dict[str, dict]:
    """Each :data:`ARMOR_NODES` name's frame in the armors' graphs
    (:data:`ARMOR_FX`), as :func:`~azurik_mod.xbr.nodes.local_matrix`
    reads it: the first transform bound to it (every transform of one
    name is authored at one frame, garret4's node at his bind: AZ-447's
    read), its translate, rotate and scale as W15 left them."""
    names, out = named_resources(fx_raw), {}
    for entry in parse_toc(fx_raw):
        if entry.tag != "node" or not names.get(entry.index, "").startswith(ARMOR_FX):
            continue
        for rec in record_offsets(fx_raw, entry.file_offset):
            if rec is None or lstr(fx_raw, rec) != "transform":
                continue
            name = bind_name(fx_raw, rec)
            if name in ARMOR_NODES and name not in out:
                attrs, _ = list_at(fx_raw, rec + 8)
                t, r, sc = (struct.unpack_from("<3f", fx_raw, attrs + 4 + 12 * j) for j in range(3))
                sp, spt, rp, rpt = (struct.unpack_from("<3f", fx_raw, rec + off) for off in (0x2C, 0x38, 0x44, 0x50))
                out[name] = {"t": t, "r": r, "s": sc, "sp": sp, "spt": spt, "rp": rp, "rpt": rpt,
                             "order": struct.unpack_from("<I", fx_raw, rec + 0x6C)[0]}
    return out


def armor_bones(characters: bytes, body: Body, points: dict[str, tuple[float, float, float]]) -> dict[str, int]:
    """The bone of ``body`` each :data:`ARMOR_NODES` piece rides, by its
    point in the model (``points``, W15's): on a body the bake maps
    (:data:`~azurik_mod.assets.retarget.MAPS`) the bone the role map
    gives garret4's (m_chest garret4's spine_2, the wrists his arm_2s);
    else the bone nearest the point on its side (by x), when within
    :data:`ARMOR_NEAR` of the body's height; else its first root bone, so
    the piece at least follows the whole body."""
    rig = Rig.read(characters, body.name)
    role: dict[str, int] = {}
    if body.name.casefold() in BAKED_BODIES:
        g4 = Rig.read(characters, PLAYER)
        by_g = {g: k for k, g in role_map(rig, g4, BAKED_BODIES[body.name.casefold()]).items()}
        index = {b.name: g for g, b in enumerate(g4.bones)}
        role = {name: by_g[index[bone]] for name, bone in ARMOR_NODES.items() if index[bone] in by_g}
    root = next(k for k, b in enumerate(rig.bones) if b.parent < 0)
    tall = body_height(characters, body)
    out = {}
    for name, t in points.items():
        if name in role:
            out[name] = role[name]
            continue
        sided = name.endswith(("Left", "Right"))
        near = min(((math.dist(p, t), k) for k, p in enumerate(rig.positions) if not sided or p[0] * t[0] > 0),
                   default=(math.inf, root))
        out[name] = near[1] if near[0] <= ARMOR_NEAR * tall else root
    return out


def armor_table(fx_raw, characters: bytes, body: Body, xbe: bytes) -> bytes:
    """X16's armor table for ``body`` (:data:`WINGS_ARMOR`): a count, then
    for each :data:`ARMOR_NODES` name the armors bind (:func:`_armor_frames`)
    its name (16 bytes), the bone it rides (:func:`armor_bones`) and C =
    F x B^-1 (16 f32, D3D rows): F its frame's local matrix as the game
    composes it (0x68BE0; ``xbe``'s Euler tables), B^-1 that bone's
    inverse bind.  The pose hook makes the piece's local C x the bone's
    matrix, so at the bind pose it is W15's F and it then moves rigidly
    with the bone.  Empty for a body with no bones."""
    frames = _armor_frames(fx_raw)
    binds = inverse_binds(characters, body.name)
    if not binds or not frames:
        return struct.pack("<i", 0)
    euler, bones = Euler(xbe), armor_bones(characters, body, {n: x["t"] for n, x in frames.items()})
    out = []
    for name, x in frames.items():
        col, inv = local_matrix(euler, x), binds[bones[name]]
        c = [sum(col[k][i] * inv[4 * k + j] for k in range(4)) for i in range(4) for j in range(4)]
        out.append(name.encode("ascii").ljust(16, b"\0") + struct.pack("<i16f", bones[name], *c))
    return struct.pack("<i", len(out)) + b"".join(out)


def install_wings_shim(xbe: bytearray, armor: bytes = b"", grown: str = "") -> None:
    """Install X16 (``player_model/wings.c``) at VAs 0x44355 and 0x44389 in
    ``xbe``: the player's body gets a virtual ``m_jump`` that the air
    armor's fx binds to, at garret4's (x, -4, 0), x his own in the anim
    playing (2 in superjump, 1 in his jumps, 0 else: Step 2.134b), with z
    5 on the first evaluation after each flap, so every flap restarts the
    wings' stroke and they fold on the ground,
    and a virtual node for each name of the ``armor`` table
    (:func:`armor_table`, written into both landings) whose pieces ride
    its bone; every other critter's binds are as before (:func:`_install`),
    but one wearing the body ``grown`` names (W27's, Step 2.134b), which
    binds no ``m_root``.  :class:`ValueError` when ``grown`` doesn't fit
    :data:`WINGS_GROWN`."""
    name = grown.encode("ascii")
    if len(name) >= WINGS_GROWN.size:
        raise ValueError(f"X16: the body name {grown!r} doesn't fit its {WINGS_GROWN.size}-byte table")
    params = {WINGS_ARMOR.name: armor, WINGS_GROWN.name: name.ljust(WINGS_GROWN.size, b"\0")}
    _install(xbe, WINGS_BIND, WINGS_SHIM, "wings bind", params)
    _install(xbe, WINGS_POSE, WINGS_SHIM, "wings pose", params)


# --- X17: no staff to sweep against the walls (Step 2.75d, AZ-441) ----------
STAFF_SWEEP_MARKER = "m_attacklevel"
"""The marker whose z (above :data:`STAFF_SWEEP_GATE`, 0x8C98F) opens the
staff-hits-wall sweep 0x8C8A0 during an attack move (state 0x100)."""
STAFF_SWEEP_GATE = 0.01
"""The z :data:`STAFF_SWEEP_MARKER` must pass for the sweep to run."""
STAFF_NODE = "staff_center2slide"
"""garret4's staff bone, the segment the sweep casts against the level;
only his body has it."""
STAFF_WALLS = PatchSpec(
    label="Player model: the staff-hits-wall sweep off (X17) at VA 0xFB9D6",
    va=0xFB9D6, abs32=(3,),
    original=bytes.fromhex("6a0168b4c01900"),   # push 1; push "combat/staff hits walls"
    patch=bytes.fromhex("6a0068b4c01900"),
)
"""X17: the default the cvar initialiser 0xFB9D0 gives ``combat/staff hits
walls`` (record 0x38BB80), whose only reader is the sweep's first test."""


def sweeps_no_staff(characters: bytes, body: Body) -> bool:
    """Whether ``body`` (in ``characters``, after B) needs X17: it has no
    :data:`STAFF_NODE`, and some clip of it raises its
    :data:`STAFF_SWEEP_MARKER` (its own, as water_lizardX's, or the one B
    adds with garret4's tracks) above :data:`STAFF_SWEEP_GATE`, so the
    sweep runs and casts a staff from stale stack bytes (0xCCDF0 writes
    no matrix for a missing node) and a hit ends the swing with no damage
    (AZ-441).  firedrake's own marker never rises, so its sweep never
    runs and its builds get no X17."""
    if STAFF_NODE in {n.casefold() for n in (*body.markers, *(bone for bone, _ in body.bones))}:
        return False
    peak = marker_peak(characters, body.name, STAFF_SWEEP_MARKER, 2)
    return peak is not None and peak > STAFF_SWEEP_GATE


def install_staff_walls_off(xbe: bytearray) -> None:
    """X17 in ``xbe`` (either release): ``combat/staff hits walls``
    defaults to 0, so 0x8C8A0 returns at its first test every tick and a
    swing ends only on its own end mark.  :class:`ValueError` when the
    site doesn't hold vanilla's bytes (D27, D35)."""
    off, original, patch = patch_spec_site(xbe, STAFF_WALLS)
    if bytes(xbe[off:off + len(original)]) != original:
        raise ValueError(f"X17: VA 0x{STAFF_WALLS.va:X} doesn't hold vanilla's cvar default; "
                         "rebuild from vanilla")
    xbe[off:off + len(patch)] = patch


# --- W40: the magic combo's finisher past its blast's reach is the beam (Step 2.197b, D797; Step 2.202, D804) ---
FINISH_RANGE = PatchSpec(
    label="Player model: a target past the blast's reach is long range (W40) at VA 0x1A2730",
    va=0x1A2730,
    original=struct.pack("<f", 0.6),   # the transition search's long-range line, read only at 0x7F0BA
    patch=struct.pack("<f", 0.6),      # the build's line (install_ranged_finisher): its blast's reach
)
"""W40's threshold: the f32 the transition search 0x7EF10 compares its
target's distance less radius (the finder's +0x18) with (``fcomp
[0x1A2730]`` at 0x7F0BA, its only reader; Europe 0x1A49D8): above it the
search's long-range byte is 1.  Its value is the build's
(:func:`finish_line`, :func:`install_ranged_finisher`): D797 (Step
2.197b) set 3 m, where the blast had stopped reaching at 0.5-1.3 m, so
from there to 3 m the finisher whiffed (2.197b's sitting: town_male_6's
blast hit at a 0.5 m gap, missed at 1 and 2); D804 (b) moves it down to
where the blast stops reaching."""
FINISH_ROW = 30
"""``attacks_transitions``' basic3 -> finish3 row (long range 0, vanilla:
finish3 within 0.6 m), which W40 makes long range 1; row 31, basic3 ->
finish (any range), plays where it doesn't match."""


def finish_line(windows, reach: float) -> float:
    """W40's line (Step 2.202, D804 (b)): how far, in metres from the
    player's feet, the finish column's blast reaches straight ahead, its
    ``windows``' farthest :attr:`~azurik_mod.assets.characters.DamageWindow.forward`
    (X3's box for the column, at the body's size) times X13's ``reach``
    for the column (its slider and W14's bump): a target whose distance
    less its radius is within it meets the blast, one past it the beam
    (whose box starts at the feet), so no gap whiffs (town_male_6's 1.30
    m, Balthazar's own 1.57, keylord's 1.00); the search meets it on the
    level since Step 2.202b (X50, AZ-803: its 3D distance had called f6's
    sentinel long range 0.15-0.3 m inside the blast's reach).
    :class:`ValueError` for a finish with no box (D35)."""
    far = max((w.forward for w in windows or ()), default=0.0) * reach
    if not (far > 0.0 and math.isfinite(far)):
        raise ValueError("W40: the finish column's blast has no box ahead to set the finisher's line by")
    return far


def ranged_finisher(transitions) -> None:
    """W40's row (D797, Step 2.197b): :data:`FINISH_ROW` (basic3 ->
    finish3) matches a long-range target, so past the build's line
    (:func:`finish_line`) the combo's last swing is finish3 (the magic's
    beam) and nearer finish
    (his blast).  :class:`XbrStructuralError` for a row that isn't
    vanilla's (D27)."""
    cols = transitions.col_names()

    def cell(row: str):
        return transitions.find_cell(cols[FINISH_ROW], row, FINISH_ROW)
    last, nxt, far = cell("last move"), cell("next move"), cell("long range")
    if (last is None or last.type_code != 2 or last.string_value != "basic3" or nxt is None or nxt.type_code != 2
            or nxt.string_value != "finish3" or far is None or far.type_code != 1 or far.double_value != 0.0):
        raise XbrStructuralError(f"W40: attacks_transitions row {FINISH_ROW} isn't vanilla's basic3 -> finish3 at "
                                 "close range: rebuild from vanilla")
    set_keyed_double(transitions, cols[FINISH_ROW], "long range", 1.0, col=FINISH_ROW)


def ranged_finisher_columns(columns: list[str], beams: int) -> bool:
    """Whether W40 applies: finish3 plays a beam (:func:`beam_columns`)
    and finish doesn't (Balthazar's combo: his blast, then his lightning)."""
    return beams >> columns.index("finish3") & 1 == 1 and not beams >> columns.index("finish") & 1


def install_ranged_finisher(xbe: bytearray, line: float) -> None:
    """W40's threshold (:data:`FINISH_RANGE`) in ``xbe`` (either release),
    ``line`` metres (:func:`finish_line`).  :class:`ValueError` when the
    site doesn't hold vanilla's 0.6 (D27, D35) or ``line`` isn't a finite
    f32."""
    off, original, _ = patch_spec_site(xbe, FINISH_RANGE)
    if bytes(xbe[off:off + len(original)]) != original:
        raise ValueError(f"W40: VA 0x{FINISH_RANGE.va:X} doesn't hold vanilla's long-range line; rebuild from "
                         "vanilla")
    if not (math.isfinite(line) and abs(line) <= FLT_MAX):
        raise ValueError(f"W40: the finisher's line {line!r} isn't a finite f32")
    xbe[off:off + 4] = struct.pack("<f", line)


# --- X50: W40's line met on the level (Step 2.202b; AZ-803, D829) ---
FINISH_RANGE_HOOK_VA = 0x7F0B2
"""The transition search's (0x7EF10) ``fld dword [esp+0x30]; mov
[esp+0x54], esi`` (Europe 0x7F062), just before its long-range compare
(``fcomp [0x1A2730]`` at 0x7F0BA), which X50 takes."""
FINISH_RANGE_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="finish_range")
FINISH_RANGE_SHIM_NAME = "player_model_finish_range"
"""Its object's name: ``player_model_finish_range.o`` in the shim build dir."""
FINISH_RANGE_HOOK = TrampolinePatch(
    name=FINISH_RANGE_SHIM_NAME,
    label=f"Player model: the finisher's line met on the level (X50) at VA 0x{FINISH_RANGE_HOOK_VA:X}",
    va=FINISH_RANGE_HOOK_VA,
    replaced_bytes=bytes(8),   # fld dword [esp+0x30]; mov [esp+0x54], esi
    shim_object=FINISH_RANGE_SHIM.object_path(FINISH_RANGE_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_finish_range",
)


def install_finish_range_shim(xbe: bytearray) -> None:
    """Install X50 (``player_model/finish_range.c``) at VA 0x7F0B2 in
    ``xbe`` (either release), with W40 (Step 2.202b; AZ-803, D829, the
    owner: "Blast where it hits, beam beyond"): the transition search
    compares W40's line, the blast box's far face, with its target's
    distance less radius on the level (the finder's distance less radius
    less its vector's height share), so the blast plays wherever its face
    reaches the target's side, whatever their heights (f6's sentinel,
    whose centre stands 1.0 m over the player's, was called long range
    0.15-0.3 m inside the blast's reach), and the beam past it
    (:func:`_install`)."""
    _install(xbe, FINISH_RANGE_HOOK, FINISH_RANGE_SHIM, "finish_range")


# --- X30: a Garret drawn larger checks his staff at his x1 size (Step 2.126, AZ-575, D317) ---
STAFF_X1 = PatchSpec(
    label="Player model: the staff-hits-wall check at x1 (X30) at VA 0x8C9CC",
    va=0x8C9CC,
    original=bytes.fromhex("8b9788010000"),   # mov edx, [edi + 0x188]: the critter's model scale
    patch=bytes.fromhex("ba0000803f90"),      # mov edx, 1.0; nop
)
"""X30: the staff check's (0x8C8A0) load of the critter's model scale,
which it pushes for 0xA3860 to scale the critter matrix's rows 0-2 before
it poses :data:`STAFF_NODE` in it (Europe 0x8C97C).  At 1.0 the staff's
two sampled ends and the sweeps between them are the x1 Garret's, its
length and its place on his drawn origin."""


def install_staff_at_x1(xbe: bytearray) -> None:
    """X30 in ``xbe`` (either release): the staff-hits-wall check poses
    garret4's staff at x1 whatever his drawn size, so a Garret drawn
    larger clanks only where a x1 one would (D317).  :class:`ValueError`
    when the site doesn't hold vanilla's bytes (D27, D35)."""
    off, original, patch = patch_spec_site(xbe, STAFF_X1)
    if bytes(xbe[off:off + len(original)]) != original:
        raise ValueError(f"X30: VA 0x{STAFF_X1.va:X} doesn't hold vanilla's scale load; rebuild from vanilla")
    xbe[off:off + len(patch)] = patch


# --- X18: the player's hit in a column garret4 hits light stuns (Step 2.104) ---
LIGHT_HIT_HOOK_VA = 0x30C1C
"""The hit-level chooser's (0x30BD0) ``TEST AH,5 / JP 0x30C26 / MOV EBX,1``
after its compare of the hit's Damage multiplier with 1.0 (0x30C11), which
X18 replaces (10 bytes)."""
_LIGHT_HIT_VANILLA = bytes(10)
LIGHT_HIT_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="light_hit")
LIGHT_HIT_SHIM_NAME = "player_model_light_hit"
"""Its object's name: ``player_model_light_hit.o`` in the shim build dir."""
LIGHT_COLUMNS = FloatParam(
    name="light_columns", symbol="_player_model_light_columns", default=0.0,
    label="Player model light-hit columns (X18)",
    description="The attacks_anims columns (a 24-bit mask) in which the player's hit stuns whatever "
                "its Damage multiplier: those whose vanilla multiplier is under 1.0.")
LIGHT_SETS_AT = BytesParam(
    name="light_sets_at", symbol="_player_model_light_sets_at", size=4,
    label="Player model light hits: X36's state (X18)")
"""X36's search landing's state (:data:`SETS_STATE`): its VA, four bytes,
so a set's swing standing for basic1-3 stuns too; 0 on a body with one set."""
LIGHT_DRAIN = "_player_model_light_drain"
"""X18's drain slot (Step 4.3, D1045): the critter X37's touch sends the
drain's hit to while it sends it, which X18 then gives the player's own
hit's level in the column playing, and whether it made it level 1 (X37
then holds its touches off that critter for the rest of the window)."""
LIGHT_HIT_HOOK = TrampolinePatch(
    name=LIGHT_HIT_SHIM_NAME,
    label=f"Player model light hits: garret4's stun in his light columns (X18) at VA 0x{LIGHT_HIT_HOOK_VA:X}",
    va=LIGHT_HIT_HOOK_VA,
    replaced_bytes=_LIGHT_HIT_VANILLA,
    shim_object=LIGHT_HIT_SHIM.object_path(LIGHT_HIT_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_light_hit",
    float_params=(LIGHT_COLUMNS,),
    bytes_params=(LIGHT_SETS_AT,),
)
LIGHT = 1.0
"""The Damage multiplier under which a hit is level 1, a stun (0x30C11
against 0x1A250C)."""


def light_columns(vanilla) -> int:
    """The ``attacks_anims`` columns (a mask) whose vanilla ``Damage
    multiplier`` (``vanilla``, the vanilla table) is under :data:`LIGHT`,
    so garret4's hit there stuns (basic1-3, right1, up1: 0.5); an empty
    cell is 1.0, the roll none."""
    return sum(1 << i for i, col in enumerate(vanilla.col_names()) if col != ROLL and (
        (cell := vanilla.find_cell(col, MULTIPLIER, i)) is not None and cell.type_code == 1
        and cell.double_value < LIGHT))


def install_light_hit_shim(xbe: bytearray, columns: int, sets_state: int = 0) -> None:
    """Install X18 (``player_model/light_hit.c``) at VA 0x30C1C in ``xbe``:
    a hit whose Damage multiplier is under 1.0 is level 1, a stun, as in
    the game, and so is the player's own melee hit in one of ``columns``
    (:func:`light_columns`) whatever its multiplier, so a balanced or
    slider-raised light attack stuns where garret4's does and the combo
    can chain; with ``sets_state`` (X36's state's VA, installed before it)
    the hit of a set's swing standing for basic1-3 too (D1045); its damage
    stays the multiplier's (:func:`_install`)."""
    _install(xbe, LIGHT_HIT_HOOK, LIGHT_HIT_SHIM, "light-hit", {LIGHT_COLUMNS.name: float(columns),
                                                                LIGHT_SETS_AT.name: struct.pack("<I", sets_state)})


def set_unstunned(columns: list[str], sets: list[list[int]], anims, carry=None) -> int:
    """The columns (a mask) a set past the first (:func:`attack_sets`)
    plays for basic1-3 whose hit doesn't stun: its written ``Damage
    multiplier`` (an empty cell 1.0) or an X10 ring entry's there at
    :data:`LIGHT` or more (``carry``, W14's), so without X18 the set's
    next attack, which needs a stunned target (rows 28-31), never follows
    it (Step 4.3, D1045: air_elemental's gust, the shards' and
    the tentacles' sweeps, beamlord's second set, the farmers' and
    booblord's sets 2-6)."""
    out = 0
    for cols in sets[1:]:
        for c in cols[:len(CHAINED)]:
            cell = anims.find_cell(columns[c], MULTIPLIER, c)
            m = cell.double_value if cell is not None and cell.type_code == 1 else 1.0
            if m >= LIGHT or any(c < len(row) and row[c] >= LIGHT for _, row in carry or ()):
                out |= 1 << c
    return out


# --- X31: the player's hits give a no-hit window shortened by the attack speed (Step 2.126, AZ-573) ---
HIT_DELAY_HOOK_VA = 0x43584
"""The critter message slot's (0x43210) ``FLD [EAX+0x10]; FST [EDX+0x1E4]``
(9 bytes, the same VA in both releases): the damage record's Delay, which
0x43591 stores into the target's no-hit timer +0x1E0 too, and which X31
replaces."""
_HIT_DELAY_VANILLA = bytes(9)
HIT_DELAY_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="hit_delay")
HIT_DELAY_SHIM_NAME = "player_model_hit_delay"
"""Its object's name: ``player_model_hit_delay.o`` in the shim build dir."""
HIT_DELAY_SCALE = FloatParam(
    name="hit_delay_scale", symbol="_player_model_hit_delay_scale", default=1.0,
    label="Player model hit window scale (X31)",
    description="What the player's hits' no-hit Delay is multiplied by: 1 / the attack speed.")
HIT_DELAY_HOOK = TrampolinePatch(
    name=HIT_DELAY_SHIM_NAME,
    label=f"Player model hits: the no-hit window over the attack speed (X31) at VA 0x{HIT_DELAY_HOOK_VA:X}",
    va=HIT_DELAY_HOOK_VA,
    replaced_bytes=_HIT_DELAY_VANILLA,
    shim_object=HIT_DELAY_SHIM.object_path(HIT_DELAY_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_hit_delay",
    float_params=(HIT_DELAY_SCALE,),
)


def shortens_hit_delay(attack_speed: float) -> bool:
    """Whether a build at ``attack_speed`` gets X31: only above 1.0 (D318's
    "Shorten the window"; the design's F1: below 1.0 Delay / speed would
    grow the window past basic2's contact, 13-17 ticks after basic1's hit
    at 0.5, where the game's lets it land)."""
    return attack_speed > 1.0


def install_hit_delay_shim(xbe: bytearray, attack_speed: float) -> None:
    """Install X31 (``player_model/hit_delay.c``) at VA 0x43584 in ``xbe``
    (either release): a hit the player deals gives its target the damage
    record's Delay times 1 / ``attack_speed`` (f32(f32(Delay) x f32(1 /
    speed)), in +0x1E0 and +0x1E4), so a faster swing's next hit lands as
    soon after the last as at x1 in its own time; every other hit (an
    enemy's, Balthazar's norm_1-3, a self hit, a platform's) keeps the
    record's (:func:`_install`)."""
    _install(xbe, HIT_DELAY_HOOK, HIT_DELAY_SHIM, "hit-delay", {HIT_DELAY_SCALE.name: 1.0 / attack_speed})


# --- X32: a worn body's plain hits show a small flash of their own (Step 2.132, D333; Step 2.180, D700) ---
HIT_FX_HOOK_VA = 0x39006
"""The AI hit handler's (0x38C60) CALL of critter_play_fx (0x440F0) with
the victim species' critters_damage_fx key for the hit's damage record
(the same VA in both releases), which X32 replaces."""
_HIT_FX_VANILLA = _call(HIT_FX_HOOK_VA, 0x440F0)
HIT_FX_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="hit_fx")
HIT_FX_SHIM_NAME = "player_model_hit_fx"
"""Its object's name: ``player_model_hit_fx.o`` in the shim build dir."""
HIT_FX_NAME_SIZE = 32
"""X32's key slot (``NAME_SIZE`` in ``player_model/hit_fx.c``)."""
HIT_FX_NAME = BytesParam(name="hit_fx", symbol="_player_model_hit_fx", size=HIT_FX_NAME_SIZE,
                         label="Player model hit effect (X32)")
HIT_FX_HOOK = TrampolinePatch(
    name=HIT_FX_SHIM_NAME,
    label=f"Player model hits: the worn body's own small hit flash (X32) at VA 0x{HIT_FX_HOOK_VA:X}",
    va=HIT_FX_HOOK_VA,
    replaced_bytes=_HIT_FX_VANILLA,
    shim_object=HIT_FX_SHIM.object_path(HIT_FX_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_hit_fx",
    bytes_params=(HIT_FX_NAME,),
)
NORM_RECORDS = 4
"""config ``damage``'s first four records, norm_1-norm_4: the plain staff's
(armor_mgr+0x18 with no power, 0x8C31B), which X32 swaps; a power's keep
their element's visual."""
HIT_FLASH = "fx/damage/v/fx_hit_small"
"""X32's flash (D700): the key the build appends it under to ``fx.xbr``."""
HIT_FLASH_SOURCE = "fx/damage/fx_norm_1"
"""The graph :data:`HIT_FLASH` copies: the plain staff's level-1 hit, one
flash of 1.17 m seen for 0.30 s (gone at 0.37 s), no particles, no sound,
no element's."""
HIT_FLASH_EDITS = ({"record": 2, "name": "NormalHit_timer", "type": "timer", "set": {"rate": 1.5},
                    "links": [{"index": 0, "factor": 0.5}, {"index": 1, "factor": 0.5}, {"index": 2, "factor": 0.5},
                              {"index": 3, "factor": 0.6}]},)
"""Its edits (``fx`` edits, :class:`~azurik_mod.assets.fx_edit.Clone`):
its timer 1.5 times as fast, its three links to the flash's scale at
half (0.58 m) and its link to the flash's gameVisible at 0.6: seen 0.20
s, gone at 0.23 s (Step 2.180's template numbers)."""


def hit_fx_type(config_xbr: bytes, species: str) -> int | None:
    """The damage record whose effect a build wearing ``species``' body
    showed on its plain hits before D700 (Step 2.132, D333), so whether
    X32 serves it (its NPC's look an element power's): the index in config
    ``damage`` of the species' critters_damage ``damageType``; ``None``
    when it has none (the townspeople), names no record (the water
    tentacles' ``watr_2``, which the game reads as norm_1), is a plain one
    (norm_1-norm_4: keylord, Balthazar, spideyzar, garret4) or every
    victim shows it as one of them (barnacle's, overlord's ``lord``)."""
    from azurkit.tools.characters.ports import load_all_tables

    tables = load_all_tables(config_xbr, sections=("damage", "critters_damage", "critters_damage_fx"))
    records, kinds, shown = tables["damage"].col_names, tables["critters_damage"], tables["critters_damage_fx"]
    kind = kinds.get_value(species, "damageType")[1] if species in kinds.entity_index else None
    if kind not in records or records.index(kind) < NORM_RECORDS:
        return None

    def key(victim: str, record: str):
        return shown.get_value(victim, record)[1] if record in shown.row_names else None
    if all(key(v, kind) in {key(v, norm) for norm in records[:NORM_RECORDS]} for v in shown.col_names):
        return None
    return records.index(kind)


def hit_flash(fx_xbr: bytes, xbe: bytes) -> list[NewResource]:
    """X32's flash (D700): vanilla ``fx_xbr``'s :data:`HIT_FLASH_SOURCE`
    copied under :data:`HIT_FLASH` with :data:`HIT_FLASH_EDITS`, the
    entries to append to ``fx.xbr`` first (numbered from its count)."""
    clone = fx_edit.Clone(fx_xbr, HIT_FLASH_SOURCE, xbe, archive="fx")
    clone.apply([dict(e) for e in HIT_FLASH_EDITS])
    return clone.build(HIT_FLASH)


def install_hit_fx_shim(xbe: bytearray, key: str = HIT_FLASH) -> None:
    """Install X32 (``player_model/hit_fx.c``) at VA 0x39006 in ``xbe``
    (either release): a plain hit the player deals (its record norm_1-
    norm_4) shows the graph ``key`` (:func:`hit_flash`'s, which the build
    appends to ``fx.xbr``) on every AI victim; a power's hit, an enemy's
    and every damage, stun and sound keep the game's (:func:`_install`).
    :class:`ValueError` for a key its slot can't hold (D35)."""
    raw = key.encode("ascii")
    if not raw or len(raw) >= HIT_FX_NAME_SIZE:
        raise ValueError(f"X32: the hit effect's key {key!r} doesn't fit its {HIT_FX_NAME_SIZE}-byte slot")
    _install(xbe, HIT_FX_HOOK, HIT_FX_SHIM, "hit-fx", {HIT_FX_NAME.name: raw + bytes(HIT_FX_NAME_SIZE - len(raw))})


# --- X43: bare hands' hits land with a thud (Step 2.159a, D502) --------------
THUD_HOOK_VA = 0x38D2F
"""The AI hit handler's (0x38C60) CALL of sound_play_at (0xA2630) with the
victim species' hit-row sound for the hit's damage record (the same VA
in both releases), which X43 replaces."""
_THUD_VANILLA = _call(THUD_HOOK_VA, 0xA2630)
THUD_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="thud")
THUD_SHIM_NAME = "player_model_thud"
"""Its object's name: ``player_model_thud.o`` in the shim build dir."""
THUD_NAME_SIZE = 32
"""X43's name slot (``NAME_SIZE`` in ``player_model/thud.c``)."""
THUD_NAME = BytesParam(name="thud", symbol="_player_model_thud", size=THUD_NAME_SIZE,
                       label="Player model hit sound (X43)")
THUD_HOOK = TrampolinePatch(
    name=THUD_SHIM_NAME,
    label=f"Player model hits: the bare-hands kit's thud (X43) at VA 0x{THUD_HOOK_VA:X}",
    va=THUD_HOOK_VA,
    replaced_bytes=_THUD_VANILLA,
    shim_object=THUD_SHIM.object_path(THUD_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_thud",
    bytes_params=(THUD_NAME,),
)


def install_thud_shim(xbe: bytearray, name: str) -> None:
    """Install X43 (``player_model/thud.c``) at VA 0x38D2F in ``xbe``
    (either release): a plain hit the player deals (its record norm_1-
    norm_4) on an AI victim plays the wave ``name`` (the kit's thud, which
    the build appends to ``fx.xbr``) in place of the victim's hit-row
    sound, when the game finds it; a power's hit, an enemy's and the
    victim's ouch keep the game's (:func:`_install`).  :class:`ValueError`
    for a name its slot can't hold (D35)."""
    raw = name.encode("ascii")
    if not raw or len(raw) >= THUD_NAME_SIZE:
        raise ValueError(f"X43: the thud's name {name!r} doesn't fit its {THUD_NAME_SIZE}-byte slot")
    _install(xbe, THUD_HOOK, THUD_SHIM, "thud", {THUD_NAME.name: raw + bytes(THUD_NAME_SIZE - len(raw))})


# --- X42: the bare-hands kit's throw (Step 2.159b; D473) ---
THROW_HOOK_VA = 0x8C3C3
"""The PlayerControl tick's (0x8C230) last CALL, of player_move_fx
(0x8C450), after the anim step (Europe 0x8C373, CALL 0x8C400), which X42
takes."""
THROW_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="throw")
THROW_SHIM_NAME = "player_model_throw"
"""Its object's name: ``player_model_throw.o`` in the shim build dir."""
THROW_TABLE = BytesParam(name="throw_table", symbol="_player_model_throw_table", size=throws.TABLE_SIZE,
                         label="Player model throw: its table (X42)")
THROW_RADIUS_AT = BytesParam(name="throw_radius_at", symbol="_player_model_throw_radius_at", size=4,
                             label="Player model throw: X21's search radius (X42)")
THROW_STATE = "_player_model_throw_state"
"""Its owner object, slots and ring in its ``.data``."""
THROW_HOOK = TrampolinePatch(
    name=THROW_SHIM_NAME,
    label=f"Player model throw: a rock or a vase from the hand (X42) at VA 0x{THROW_HOOK_VA:X}",
    va=THROW_HOOK_VA,
    replaced_bytes=_call(THROW_HOOK_VA, 0x8C450),
    shim_object=THROW_SHIM.object_path(THROW_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_throw",
    bytes_params=(THROW_TABLE, THROW_RADIUS_AT),
)


def install_throw_shim(xbe: bytearray, table: bytes, radius: int) -> None:
    """Install X42 (``player_model/throw.c``) at VA 0x8C3C3 in ``xbe``
    (either release) with the throw's ``table``
    (:meth:`~azurik_mod.patches._player_throw.Plan.table`) and X21's
    search radius at ``radius`` (a VA): a swing of the table's column
    spawns its species in the right hand, throws it at its release
    straight along the facing to the table's miss point (a table with
    ``seek``: onto the critter nearest the facing within its range and
    cone, X21's radius raised to it for the call; D761), sends its hits as
    the player's and drops it when the swing is cut (:func:`_install`).
    :class:`ValueError` for a table of another size (D35)."""
    if len(table) != throws.TABLE_SIZE:
        raise ValueError(f"X42: a {len(table)}-byte table, not {throws.TABLE_SIZE}")
    _install(xbe, THROW_HOOK, THROW_SHIM, "throw",
             {THROW_TABLE.name: table, THROW_RADIUS_AT.name: struct.pack("<I", radius)})


def projectile_row(worn, lo, who: str):
    """The build's one projectile ``effects`` row (Step 2.167b, D538's
    E2; :func:`~azurik_mod.assets.fx_templates.effects`): its recipe's
    (``worn``, the recipe the build plays) or its weapon style's, else
    ``None``; two that differ are refused by name (X42 throws one
    species a build, ``debug``)."""
    rows = [("its recipe", e) for e in (worn.effects if worn is not None else ()) if e.template.engine == "throw"]
    style = lo.weapon.style if lo.weapon is not None else None
    if style is not None and style.effects:
        rows += [(f"its weapon {lo.weapon.name}'s style {style.name}", e) for e in style.effects
                 if e.template.engine == "throw"]
    distinct = [(w, e) for k, (w, e) in enumerate(rows) if all(e != f for _, f in rows[:k])]
    if len(distinct) > 1:
        (w1, e1), (w2, e2) = distinct[:2]
        raise ValueError(f"--player-character {who!r}: {w1} throws {e1.template.name} on "
                         f"{', '.join(e1.columns)} and {w2} {e2.template.name} on {', '.join(e2.columns)}: X42 "
                         f"throws one species a build ({throws.SPECIES}, W30), so one projectile row")
    return distinct[0][1] if distinct else None


def bound_rows(worn, lo, who: str) -> list:
    """The build's shield and beam ``effects`` rows (Step 2.167c, D538's
    E3; X38's bound keys): its recipe's, then its weapon style's (one the
    same as a recipe's taken once); a column two of them name, or more
    than :data:`~azurik_mod.assets.fx_templates.BOUND_ROWS` rows, is
    refused by name."""
    rows = [("its recipe", e) for e in (worn.effects if worn is not None else ()) if e.template.engine == "bound"]
    style = lo.weapon.style if lo.weapon is not None else None
    if style is not None and style.effects:
        rows += [(f"its weapon {lo.weapon.name}'s style {style.name}", e) for e in style.effects
                 if e.template.engine == "bound"]
    out: list[tuple[str, object]] = []
    for w, e in rows:
        if any(e == f for _, f in out):
            continue
        for v, f in out:
            both = sorted(set(e.columns) & set(f.columns))
            if both:
                raise ValueError(f"--player-character {who!r}: {v}'s {f.template.name} row and {w}'s "
                                 f"{e.template.name} row both play on {both[0]} (a column plays one effect)")
        out.append((w, e))
    if len(out) > fx_templates.BOUND_ROWS:
        raise ValueError(f"--player-character {who!r}: {len(out)} shield and beam rows (its recipe's and its "
                         f"style's): X38's table holds {fx_templates.BOUND_ROWS} bound keys")
    return [e for _, e in out]


def bound_place(characters: bytes, body: Body, garret4: Body, point: ActionPoint, anims, columns: list[str],
                picks: list[str], style_hits: dict, drawn: float, effect
                ) -> tuple[str | None, tuple[float, float, float], float]:
    """Where a bound row's holder goes (Step 2.167c): (the marker it
    binds, its place in model units, its scale).  ``centre`` and
    ``front``: :data:`~azurik_mod.patches._player_fx_ring.CENTRE`, which
    places and sizes it with the body (garret4's own m_root, X16's on any
    other: its W15 size); ``feet``: unbound at the model's origin, sized
    by the body's height over garret4's; ``hand``: unbound at the action
    point (D219: the hand bone where it reaches farthest ahead in each of
    the row's columns' clips' first damage window, else at 0.4 of the
    clip, averaged; its bind pose's where no column's clip is the body's
    own; a fixed point for a body without a hand) in the model's axes
    (ahead +y), scaled 1 / ``drawn``, so its lengths are metres."""
    role = effect.template.anchor
    if role in ("centre", "front"):
        return fx_ring.CENTRE, (0.0, 0.0, 0.0), 1.0
    if role == "feet":
        return None, (0.0, 0.0, 0.0), body_height(characters, body) / body_height(characters, garret4)
    if point.kind != "hand":
        return None, point.point, 1.0 / drawn
    rig = Rig.read(characters, body.name)
    toc = parse_toc(characters)
    keys = {name.casefold(): i for i, name in named_resources(characters).items()}
    seen = []
    for name in effect.columns if picks else ():
        key = f"characters/{body.name}/{picks[columns.index(name)]}".casefold()
        if key not in keys:
            continue
        motion = read_clip(characters, toc[keys[key]].file_offset)
        hits = style_hits.get(picks[columns.index(name)]) or damage_windows(characters, body.name,
                                                                            picks[columns.index(name)], drawn)
        first = min(hits, key=lambda w: w.on) if hits else None
        times = ([first.on + (first.off - first.on) * j / 8 for j in range(9)] if first is not None
                 else [0.4 * motion.length])
        seen.append(max((origins(rig, motion, t)[point.bone] for t in times), key=lambda o: o[1]))
    if not seen:
        seen = [origins(rig, Clip(1.0, (), ()), 0.0)[point.bone]]
    return None, tuple(sum(c) / len(seen) for c in zip(*seen)), 1.0 / drawn


def shot_timing(characters: bytes, body: Body, garret4: Body, anims, columns: list[str], picks: list[str],
                style_hits: dict, drawn: float, shot) -> dict[int, tuple[int, int | None]]:
    """Each of a projectile row's columns (Step 2.167b): its clip's ticks
    at 30 Hz (the pick's, :func:`source_clip`; a clipless body's
    garret4's) and the tick its first damage window opens (X3's for a
    style's clip, else its markers'), ``None`` for none."""
    out = {}
    for name in shot.columns:
        if name not in columns:
            continue   # template_plan names it
        i = columns.index(name)
        pick = picks[i] if picks else anims.find_cell(name, "Anim", i).string_value
        owner, clip = source_clip(body, garret4, pick) if picks else (garret4, pick)
        ticks = max(1, round(owner.length(clip) * 30.0))
        hits = style_hits.get(pick) or damage_windows(characters, owner.name, clip, drawn)
        out[i] = (ticks, round(min(w.on for w in hits) * 30.0) if hits else None)
    return out


def throw_bone(characters: bytes, body: Body, lo, picks: list[str]) -> int:
    """The bone a projectile row's projectile is held at (Step 2.167b):
    the build's grip (a creature's, Step 2.161e), else its right hand,
    else W6's hand, else -1 (X42's point ahead of the chest)."""
    names = [b.name for b in Rig.read(characters, body.name).bones]
    point = action_point(characters, body, picks)
    for name in (lo.grip, throws.HAND, *(point.hands or ())):
        if name and name in names:
            return names.index(name)
    return -1


# --- X33: flyers and spins attack while moving (Step 2.132, D334, D346, D351) ---
CARRY_HOOK_VA = 0x8C728
"""player_attack_root_motion's (0x8C630) CALL of move_query_clear (0x307E0)
before it hands the move code the attack's velocity (Europe 0x8C6D8),
which X33 replaces."""
_CARRY_VANILLA = _call(CARRY_HOOK_VA, 0x307E0)
CARRY_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="attack_carry")
CARRY_SHIM_NAME = "player_model_attack_carry"
"""Its object's name: ``player_model_attack_carry.o`` in the shim build dir."""
CARRY_COLUMNS = FloatParam(
    name="carry_columns", symbol="_player_model_carry_columns", default=0.0,
    label="Player model attack columns that move with the stick (X33)",
    description="The attacks_anims columns (bit i: column i) whose swing takes the stick's "
                "run velocity and the walk's turn; 0 none.")
HELD_COLUMNS = FloatParam(
    name="held_columns", symbol="_player_model_held_columns", default=0.0,
    label="Player model attack columns that repeat while held (X33)",
    description="The attacks_anims columns (bit i: column i) that X33's held entries chain while their "
                "button is held, never carried (W23's thrown gust, Step 2.145, D414); 0 none.")
CARRY_HOOK = TrampolinePatch(
    name=CARRY_SHIM_NAME,
    label=f"Player model attacks: moving with the stick (X33) at VA 0x{CARRY_HOOK_VA:X}",
    va=CARRY_HOOK_VA,
    replaced_bytes=_CARRY_VANILLA,
    shim_object=CARRY_SHIM.object_path(CARRY_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_attack_carry",
    float_params=(CARRY_COLUMNS, HELD_COLUMNS),
)


def _carry_entry(what: str, va: int, target: int, symbol: str, label: str) -> TrampolinePatch:
    """One of X33's entries (Step 2.140): ``attack_carry.c``'s ``symbol``
    at the CALL of ``target`` at ``va``, with X33's mask."""
    return TrampolinePatch(
        name=f"{CARRY_SHIM_NAME}_{what}",
        label=f"Player model attacks: {label} (X33) at VA 0x{va:X}",
        va=va,
        replaced_bytes=_call(va, target),
        shim_object=CARRY_SHIM.object_path(CARRY_SHIM_NAME, CHECKOUT),
        shim_symbol=symbol,
        float_params=(CARRY_COLUMNS, HELD_COLUMNS),
    )


CARRY_ENTRIES = (
    _carry_entry("held_a", 0x8D3E5, 0xA30D0, "_c_player_model_attack_held", "a held A repeats"),
    _carry_entry("held_b", 0x8D406, 0xA30D0, "_c_player_model_attack_held", "a held B repeats"),
    _carry_entry("air", 0x8D38A, 0x88E70, "_c_player_model_attack_air", "a held button attacks in the air"),
    _carry_entry("jump", 0x8D46F, 0x8C7D0, "_c_player_model_attack_jump", "a jump cancels into the air"),
    _carry_entry("land", 0x89982, 0x85920, "_c_player_model_attack_land", "an air attack ends at its landing"),
    _carry_entry("ground_jump", 0x8D15A, 0x89060, "_c_player_model_attack_ground_jump",
                 "a swing that ends in the air can't jump"))
"""X33's entries beside :data:`CARRY_HOOK` (Step 2.140; D377, D380, D381,
D383; Europe 0x8D395, 0x8D3B6, 0x8D33A, 0x8D41F, 0x89932): the attack
state's CALLs of ``button_pressed_once`` (0xA30D0) at 0x8D3E5 (A) and
0x8D406 (B), the airborne state's CALL of ``player_air_attack_start``
(0x88E70) at 0x8D38A, the attack state's CALL of
``player_ground_attack_tick`` (0x8C7D0) at 0x8D46F and the airborne
tick's CALL of ``player_land_classify`` (0x85920) at 0x89982; and state
0's CALL of ``player_jump_init`` (0x89060) at 0x8D15A (Europe 0x8D10A;
Step 2.145, D413, AZ-630), which jumps only with a ground contact."""
FLYERS = frozenset({
    "bird", "air_octopus", "bot", "fire_bot", "channeler", "firedrake", "firefly", "overlord and gargoyle",
    "shard", "fire_shard", "air_elemental", "air_elemental_boss", "fire_elemental", "blaze_sentinel",
    "blaze_move", "guard_air", "guard_air_clone"})
"""The species that fly or hover as NPCs (D334, D335, D351; Step 2.132's
read of the NPCs' effects and moves): the
flocking flyers with fly clips of their own (bird, the air octopus, the
bots, the channeler, the firedrake, the firefly, the gargoyle, the shard;
fire_shard flocks with none), the hoverers whose walk, run and idle hold
every bone off the floor (the elementals, the blaze sentinel) and the air
boss.  Not the fish (swimmers) nor rock, ice and lava_shard, which read as
floating in their clips unconfirmed (D115's default: out until a sitting
sees them float)."""
SPIN_CLIPS = frozenset({
    ("bosses/air_guardian", "attack_wind"), ("blaze_sentinel", "attack"), ("rock_shard", "attack_3"),
    ("ice_shard", "attack_3"), ("water_lizardX", "attack_1"),
    (PLAYER, "360_basic_attack"), (PLAYER, "360_sweep"), (PLAYER, "360_ledge")})
"""The spin attacks (D351), by body and clip: the clips whose bones turn
270 degrees or more about the body over the clip (Step 2.132's read, its
``spins`` measure: guard_air's attack_wind +364, the blaze sentinel's
attack -360, the shards' attack_3 +360, the sleeths' attack_1 +424,
garret4's 360_basic_attack, 360_sweep and 360_ledge, for a baked pick of
them).  A table, not a build-time measure (D115: a yaw fit reads noisy on
flat skeletons): barnacle's attack_1-3 and watertentacle_02's attack_l2
read as spins unsure, so they stay out."""


def carry_mask(species: str, body: Body, columns: list[str], picks: list[str],
               rotate: tuple[list[int], int] | None = None) -> int:
    """X33's columns for an own-mode build wearing ``species``' ``body``
    (D351: floaters and spins attack while moving; walkers keep the game's
    stop-and-swing): every attack column but the roll for a :data:`FLYERS`
    species; else each column whose clip is a spin (:data:`SPIN_CLIPS`,
    ``picks`` through :func:`source_clip`; a column X10 turns, ``rotate``,
    only when every clip of its ring is).  0 for a body with no clips."""
    if not picks:
        return 0
    if species in FLYERS:
        return sum(1 << i for i, col in enumerate(columns) if col != ROLL)
    ring, turns = rotate or ([], 0)

    def spins(pick: str) -> bool:
        owner, clip = (PLAYER, pick[len(BAKED_DIR):]) if pick.startswith(BAKED_DIR) else (body.name, pick)
        return (owner, clip) in SPIN_CLIPS
    return sum(1 << i for i, col in enumerate(columns) if col != ROLL and (
        all(spins(picks[h]) for h in ring) if turns >> i & 1 else spins(picks[i])))


def install_attack_carry_shim(xbe: bytearray, columns: int, held: int = 0) -> None:
    """Install X33 (``player_model/attack_carry.c``) at VA 0x8C728 and its
    entries (:data:`CARRY_ENTRIES`) in ``xbe``: a swing on the ground in a
    column of ``columns`` (a mask; never the roll's) whose own slot plays
    adds garret4's runSpeed times the stick's magnitude along its
    direction to the clip's root motion and faces the body the walk's way
    that tick, a held A or B reads as a press (so it chains), a jump
    press jumps at once, and a swing that ends in the air (carried off a
    ledge) can't jump until it lands; with the jump attack's column (13) in the mask
    the jump goes on as the air attack, a held button attacks in the air,
    an air attack's entry keeps the jump's velocity and its landing ends
    it at once (state 0, a held button chaining on the ground); a column
    of ``held`` (never carried: W23's thrown gust) chains on its held
    button too, and nothing else; every other move is the game's
    (:func:`_install`)."""
    params = {CARRY_COLUMNS.name: float(columns), HELD_COLUMNS.name: float(held)}
    for hook in (CARRY_HOOK, *CARRY_ENTRIES):
        _install(xbe, hook, CARRY_SHIM, "attack-carry", params)


# --- X34: a player body touches pickups at its size (Step 2.133; D344, D356) ---
TOUCH_HOOK_VA = 0x8C553
"""The player tick's (0x8C520) ``MOV EDX, [0x1980BC]; PUSH 0x80; PUSH EDX;
PUSH EDX`` (13 bytes; Europe 0x8C503, its radius at 0x19A264): the pickup
query's mask and its horizontal and vertical radii (collision_sweep's
args 6 and 7), both the one constant 1.0, which X34 replaces."""
_TOUCH_VANILLA = bytes(13)
TOUCH_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="touch")
TOUCH_SHIM_NAME = "player_model_touch"
"""Its object's name: ``player_model_touch.o`` in the shim build dir."""
TOUCH_XY = FloatParam(
    name="touch_xy", symbol="_player_model_touch_xy", default=1.0,
    label="Player model touch, horizontal (X34)",
    description="The pickup query's horizontal radius, m: the body's size s.")
TOUCH_Z = FloatParam(
    name="touch_z", symbol="_player_model_touch_z", default=1.0,
    label="Player model touch, vertical (X34)",
    description="The pickup query's vertical radius, m: sqrt(s) above 1, s below.")
TOUCH_DZ = FloatParam(
    name="touch_dz", symbol="_player_model_touch_dz", default=0.0,
    label="Player model touch, centre (X34)",
    description="How far the query's centre moves from the body's (feet + 1 m), m: 0 above 1, s - 1 below.")
TOUCH_HOOK = TrampolinePatch(
    name=TOUCH_SHIM_NAME,
    label=f"Player model touch: the pickup query at the body's size (X34) at VA 0x{TOUCH_HOOK_VA:X}",
    va=TOUCH_HOOK_VA,
    replaced_bytes=_TOUCH_VANILLA,
    shim_object=TOUCH_SHIM.object_path(TOUCH_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_touch",
    float_params=(TOUCH_XY, TOUCH_Z, TOUCH_DZ),
)


def touch_query(s: float) -> tuple[float, float, float]:
    """X34's (horizontal radius, vertical radius, centre's z offset), m,
    for a body of size ``s`` (:func:`body_size`): above 1 (s, sqrt(s), 0),
    garret4's centre with a radius that contains his test and reaches
    sqrt(s) - 1 m deeper under the feet (2.133's critique, finding 4: rule
    S); below 1 (s, s, s - 1), his test scaled about the feet, so an item
    resting on the floor stays touchable (the design's C3); 1 is his."""
    return (s, math.sqrt(s), 0.0) if s >= 1.0 else (s, s, s - 1.0)


def touch_words(s: float) -> str:
    """The build log's words for X34 at size ``s``."""
    xy, z, dz = touch_query(s)
    return (f"it touches pickups {xy:.3g} m round its centre and {z:.3g} m up and down"
            + (f", the centre {-dz:.3g} m lower" if dz else "") + " (X34)")


WALK_SPEED = "walkSpeed"
"""garret4's ``critters_critter_data`` cell (CritterData +0x38, read at
0x49D7E) the player reads as the walk/run switch: below it the walk clip
(0x864AA) and the standing take-off (0x89216), past it the run's and the
running one, a ground attack's "last move: run" rows (0x88C14), the idle
under 0.1 x it (0x86474) and the vertical swim's speed (0x8B8C5)."""


def write_walk_speed(game, doc, s: float) -> float:
    """Write garret4's :data:`WALK_SPEED` in ``doc`` (``game``'s config
    document) for a body of size ``s`` (Step 2.145, D422, AZ-617): his
    vanilla one (5.0) x sqrt(s), as the size fold scales his runSpeed
    (``layer.size_params``), so a full-stick run stays past it (7 / 5 at
    the walk slider's 1) at every size and plays the run clip and a
    running take-off (below s 0.51 it played the walk clip fast and the
    standing take-off), and the dive and rise go that fast.  No logic
    number reads it (the movement model has no walkSpeed).  Returns it."""
    vanilla = XbrDocument.from_bytes(game.stored("config.xbr")).keyed_section("critters_critter_data").find_cell(
        PLAYER, WALK_SPEED, None).double_value
    walk = vanilla * math.sqrt(s)
    set_keyed_double(doc.keyed_section("critters_critter_data"), PLAYER, WALK_SPEED, walk)
    return walk


def walk_words(walk: float) -> str:
    """The build log's words for :func:`write_walk_speed`'s ``walk``."""
    return f"its walk/run switch and dive at {walk:.3g} m/s (garret4's walkSpeed x sqrt(s))"


def install_touch_shim(xbe: bytearray, s: float) -> None:
    """Install X34 (``player_model/touch.c``) at VA 0x8C553 in ``xbe``
    (either release): the player's pickup query takes :func:`touch_query`'s
    radii and centre for size ``s``, so a body touches what its drawn size
    touches (D344, D356; :func:`_install`)."""
    _install(xbe, TOUCH_HOOK, TOUCH_SHIM, "touch", dict(zip(
        (TOUCH_XY.name, TOUCH_Z.name, TOUCH_DZ.name), touch_query(s))))


# --- X36: WHITE cycles a swapped body's attack sets (Step 2.135; D325, D326, D352) ---
SETS_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="attack_sets")
SETS_SHIM_NAME = "player_model_attack_sets"
"""Its object's name: ``player_model_attack_sets.o`` in the shim build dir."""
SETS_LINE = 80
"""Bytes a set's line takes in X36's table (79 characters and a NUL)."""
SETS_MAP = BytesParam(
    name="sets_map", symbol="_player_model_sets_map", size=1 + SETS_MAX * len(SET_COMBO),
    label="Player model attack sets: their count and each set's columns (X36)")
"""The set count, then per set the column each of :data:`SET_COMBO`
plays (set 0 each its own; a set's finisher in finish, finish2 and
finish3)."""
SETS_LINES = BytesParam(
    name="sets_lines", symbol="_player_model_sets_lines", size=SETS_MAX * SETS_LINE,
    label="Player model attack sets: each set's line (X36)")
SETS_STATE_AT = BytesParam(
    name="sets_state_at", symbol="_player_model_sets_state_at", size=4,
    label="Player model attack sets: the search landing's state (X36)")
"""The white and HUD landings' pointer to the search landing's state (each
hook lands its own copy of ``attack_sets.c``): its VA, four bytes; 0 in
the search's own landing."""
SETS_MATERIAL = BytesParam(
    name="sets_material", symbol="_player_model_sets_material", size=4,
    label="Player model attack sets: the 2D material's VA (X36)")
"""The HUD landing's pointer to the game's 2D material (:data:`HUD_MATERIAL_VA`
in the build's release, Europe 0x974F0): its VA, four bytes."""
HUD_MATERIAL_VA = 0x97420
"""The game's 2D material (ESI the RGBA, EDI the texture handle's address,
stdcall(0, 1) for text, RET 8; AL 0 on failure), which X36's HUD line sets
before its text.  Its first instruction is ``MOV EAX, imm32``, a byte the
vanilla-symbol registry's prologue check doesn't take, so the build hands
its release's VA to the shim instead (Step 2.153)."""
SETS_STATE = "_player_model_sets_state"
"""The state's symbol in the search's landing: the set, the combo column a
set's swing stands for and its column, the last press's time."""
SETS_HOOKS = tuple(TrampolinePatch(
    name=f"{SETS_SHIM_NAME}_{what}",
    label=f"Player model attacks: {why} (X36) at VA 0x{va:X}",
    va=va,
    replaced_bytes=_call(va, target),
    shim_object=SETS_SHIM.object_path(SETS_SHIM_NAME, CHECKOUT),
    shim_symbol=f"_c_player_model_attack_sets_{what}",
    bytes_params=(SETS_MAP, SETS_LINES, SETS_STATE_AT, SETS_MATERIAL),
) for what, why, va, target in (
    ("search", "the set WHITE selected plays", 0x88D78, 0x7EF10),
    ("white", "WHITE selects the next set", 0x854B4, 0x84940),
    ("hud", "the set's line in the HUD's top-left corner", 0x1B306, 0x1B110)))
"""X36's landings, the search's first (its state the others'): the ground
attack start's (0x88A80) CALL of attack_transition_search (0x7EF10) at
0x88D78 (Europe 0x88D28), player_input_build's (0x84F90) CALL of
player_input_tick (0x84940) at 0x854B4 (Europe 0x85464), every
PlayerControl tick, and the HUD draw's (0x1B2B0) CALL of hud_list_draw
(0x1B110) at 0x1B306 (the same in Europe), its last draw."""
DIRECTION_EDITS = (
    PatchSpec(label="Player model attacks: no up or down row (X36) at VA 0x7EF90", va=0x7EF90,
              original=bytes.fromhex("7457"), patch=bytes.fromhex("eb57")),     # je -> jmp 0x7EFE9
    *(PatchSpec(label=f"Player model attacks: no {side} row (X36) at VA 0x{va:X}", va=va,
                original=bytes.fromhex("c7442458") + struct.pack("<I", vanilla),
                patch=bytes.fromhex("c7442458") + struct.pack("<I", 1))
      for side, va, vanilla in (("back", 0x7F08B, 4), ("right", 0x7F09B, 2), ("left", 0x7F0AA, 3))))
"""X36's byte edits in attack_transition_search (0x7EF10; Europe each
0x50 lower): the target-found branch's ``je`` at 0x7EF90 to the bearing
path, so the up/down classification (5, 6) never runs, and the three
``mov dword [esp+0x58], imm32`` of the bearing path writing back (4),
right (2) and left (3) write forward (1), so rows 15-26 never match and
the combo's forward rows 28-31 need none (:data:`CHAIN_GATES`), 32 only
its target features; the 60 deg target gate and the swing's yaw stay the
game's."""
CHAIN_GATES = (28, 29, 30, 31)
"""The ``attacks_transitions`` columns (the combo's chain rows: basic1 ->
basic2, basic2 -> basic3, basic3 -> finish3 and basic3 -> finish) whose
``target features`` cell ("stunned frozen") a build with ``chain`` "any"
clears on any body (Step 4.3, D1045, the owner: "make it default not
chain on any press, with the option to turn on the chain on any press,
for any model"; Step 2.153's D432 cleared it on every X36 body): 0x7F137
reads an empty mask as no gate.  By default ("hit") they keep it, so the
combo goes on only onto the target the last attack stunned, as
garret4's (X18 stuns a set's swings too).  Column 32 (finish2 on a
stunned target, searched before row 35, so cleared it would play on
every fresh press) and 16 keep theirs; Europe reads the same
``config.xbr``."""


def lift_chain_gates(doc) -> None:
    """``chain`` "any" (D1045) in ``doc`` (config.xbr's): :data:`CHAIN_GATES`'
    ``target features`` cleared, so the combo's next attack follows a
    press in its window, hit or miss."""
    transitions = doc.keyed_section("attacks_transitions")
    for c in CHAIN_GATES:
        clear_keyed_cell(transitions, "a", "target features", col=c)


def install_attack_sets_shim(xbe: bytearray, sets: list[list[int]], lines: list[str]) -> None:
    """Install X36 (``player_model/attack_sets.c``) at VAs 0x88D78, 0x854B4
    and 0x1B306 in ``xbe`` (either release) with :data:`DIRECTION_EDITS`:
    a WHITE press (not swimming, not while the presses wait) selects the
    next of ``sets`` (:func:`attack_sets`) and for 2.0 s shows its line of
    ``lines`` (:func:`set_lines`) in the HUD's top-left corner, yellow at
    0.8 (D441);
    in a set other than the first, the combo's basic1-3 and finishers play
    the set's columns (their whole records and yaw, the target kept), the
    next search keyed on the combo's place; direction picks no attack
    (:func:`_install`).  :class:`ValueError` (D35) for more sets than
    :data:`SETS_MAX` or none, a line that doesn't fit, or an edit site
    that doesn't hold vanilla's bytes (D27), before anything is written."""
    if not 1 <= len(sets) <= SETS_MAX or len(lines) != len(sets):
        raise ValueError(f"X36: {len(sets)} attack sets and {len(lines)} lines; 1 to {SETS_MAX} sets, a line each")
    raw = [line.encode("ascii") for line in lines]
    if any(len(r) >= SETS_LINE for r in raw):
        raise ValueError(f"X36: an attack set's line is past {SETS_LINE - 1} characters")
    sites = [patch_spec_site(xbe, spec) for spec in DIRECTION_EDITS]
    for spec, (off, original, _) in zip(DIRECTION_EDITS, sites):
        if bytes(xbe[off:off + len(original)]) != original:
            raise ValueError(f"X36: VA 0x{spec.va:X} doesn't hold vanilla's direction code; rebuild from vanilla")
    for off, _, patch in sites:
        xbe[off:off + len(patch)] = patch
    table = bytes([len(sets)]) + bytes(range(len(SET_COMBO))) + b"".join(
        bytes(cols[:3] + [cols[3]] * (len(SET_COMBO) - 3)) for cols in sets[1:])
    params = {SETS_MAP.name: table, SETS_LINES.name: b"".join(r.ljust(SETS_LINE, b"\0") for r in raw)}
    search, *others = SETS_HOOKS
    _install(xbe, search, SETS_SHIM, "attack-sets", params)
    state = trampoline_symbol_va(xbe, search, SETS_STATE, CHECKOUT, shim_source=SETS_SHIM.source_path())
    material = struct.pack("<I", xbe_layout(xbe).va(HUD_MATERIAL_VA))
    for hook in others:
        _install(xbe, hook, SETS_SHIM, "attack-sets", params | {
            SETS_STATE_AT.name: struct.pack("<I", state), SETS_MATERIAL.name: material})


# --- X37: Balthazar's drain beam drains the enemy it lands on (Step 2.135; D324, D357; Step 2.153, D452) ---
DRAIN_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="drain")
DRAIN_SHIM_NAME = "player_model_drain"
"""Its object's name: ``player_model_drain.o`` in the shim build dir."""
DRAIN_SHARE = 1.0
"""The share of the damage the drain deals that comes back as the wearer's
HP (D452: "let's make it heal 100%", superseding D357's 25 %, Step 2.153):
norm_2's 15 for every enemy its box touches, once a window each (after the
drain's hit an enemy takes no hit for 2.6-2.9 s; X37 passes a common AI
critter's shorter window once, so the hits of the chain's first swings
don't void it)."""
DRAIN_RANGE = 16.0
"""How far, in metres (distance less radius), the worn drain looks for
its target, at any bearing (D452: "a bigger and wider range so that it
does not miss much"; D115's default, Step 2.153: past beamlord's 14 m
beam)."""
DRAIN_COLUMNS = FloatParam(
    name="drain_columns", symbol="_player_model_drain_columns", default=0.0,
    label="Player model drain columns (X37)",
    description="The attacks_anims columns (bit i: column i) whose clip switches the body's own drain on.")
DRAIN_SHARE_PARAM = FloatParam(
    name="drain_share", symbol="_player_model_drain_share", default=DRAIN_SHARE,
    label="Player model drain heal share (X37)",
    description="The share of the HP the drain takes from a critter that the wearer gains.")
DRAIN_RANGE_PARAM = FloatParam(
    name="drain_range", symbol="_player_model_drain_range", default=DRAIN_RANGE,
    label="Player model drain range (X37)",
    description="How far, in metres, the drain looks for the critter it lands on.")
DRAIN_EVERY = FloatParam(
    name="drain_every", symbol="_player_model_drain_every", default=0.0,
    label="Player model drain takes every critter (X37)",
    description="1: the drain takes life from every critter its box touches (drain.targets all); 0: from its "
                "target alone.")
DRAIN_TARGETS = ("nearest", "all")
"""A recipe's or weapon style's ``drain.targets`` (AZ-758, Step 2.196,
D765: "can you make it just drain the nearest? Although having multi
enemy target attacks like this is cool, for future weapons"): ``nearest``
(the default) the drain takes life from the critter attack_target_find
picks alone; ``all`` from every critter its box touches (Step 2.153's:
beamlord's recipe, D782: "beamlord keeps the area drain, balthazar
drains one target")."""
DRAIN_CHEST = FloatParam(
    name="drain_chest", symbol="_player_model_drain_chest", default=0.0,
    label="Player model drain stream's chest (X37)",
    description="How far over the player's model origin, in metres, the drain stream's pull and sink sit before a "
                "clip lifts him (0: no stream).")
DRAIN_BONES = FloatParam(
    name="drain_bones", symbol="_player_model_drain_bones", default=0.0,
    label="Player model drain: the body's bones (X37)",
    description="How many posed bones the drain stream reads for how far a clip lifts the player.")
DRAIN_FEET = FloatParam(
    name="drain_feet", symbol="_player_model_drain_feet", default=0.0,
    label="Player model drain: the body's lowest bind bone (X37)",
    description="The bind pose's lowest bone height, in model units: a lift is the posed lowest less it.")
DRAIN_DRAWN = FloatParam(
    name="drain_drawn", symbol="_player_model_drain_drawn", default=1.0,
    label="Player model drain: metres a model unit (X37)",
    description="The body's drawn scale, which turns its posed lift into metres.")
DRAIN_SINK = FloatParam(
    name="drain_sink", symbol="_player_model_drain_sink", default=0.0,
    label="Player model drain: the stream's box sink height (X37)",
    description="The drain stream's box sink height standing, in metres, which X37 makes taller by a clip's lift "
                "so it spans the standing chest to the lifted one (0: kept).")
DRAIN_BEAMS = FloatParam(
    name="drain_beams", symbol="_player_model_drain_beams", default=0.0,
    label="Player model beam columns (X37)",
    description="The attacks_anims columns (bit i: column i) whose clip switches the beam's lightning on (AZ-769).")
DRAIN_AIM_REACH = FloatParam(
    name="drain_aim_reach", symbol="_player_model_drain_aim_reach", default=0.0,
    label="Player model beam's reach (X37)",
    description="How far ahead of the player, in metres, the beam's bolts reach with no target, and how far the "
                "beam looks for one (AZ-769).")
DRAIN_AIM_CHEST = FloatParam(
    name="drain_aim_chest", symbol="_player_model_drain_aim_chest", default=0.0,
    label="Player model beam's height (X37)",
    description="How high over the player's model origin, in metres, the beam's bolts reach with no target.")
DRAIN_AIM_HALF = FloatParam(
    name="drain_aim_half", symbol="_player_model_drain_aim_half", default=0.0,
    label="Player model beam's half-width (X37)",
    description="How far either side of the swing's line, in metres, a critter stands in the beam's box (its "
                "radius added) for the bolts to go on it (the review's F2).")
DRAIN_AIM = BytesParam(
    name="drain_aim", symbol="_player_model_drain_aim", size=4,
    label="Player model beam's bolt targets (X37)")
"""The aim nodes (AZ-769, Step 2.197b): their count, then each one's record
in the player's clone of the graph (:data:`BEAM_AIM`'s inherit-7 locators);
zeros: none."""
BEAM_AIM = ("locator1", "locator2", "locator3")
"""Balthazar's bolts' three targets in his default fx (records 58, 60 and
62: the pBurstEmitter [24]'s pNull targets [59], [61], [63] under them),
which his own build's overlay (W23, and W34's clone of it) makes inherit
mode 7 so X37's anchor places them on the beam's target (AZ-769, D797)."""
BEAM_REACH, BEAM_HALF = 6.0, 0.5
"""The beam's reach and half-width, in metres, where the build's beam
columns hold no box of their own to read (its box's far face straight
ahead and its farthest side otherwise)."""
DRAIN_RADIUS_AT = BytesParam(
    name="drain_radius_at", symbol="_player_model_drain_radius_at", size=4,
    label="Player model drain: X21's search radius (X37)")
"""X21's writable radius (:data:`SEARCH_RADIUS_SYMBOL`), which
attack_target_find's seven operands read: its VA, four bytes."""
DRAIN_STATE_AT = BytesParam(
    name="drain_state_at", symbol="_player_model_drain_state_at", size=4,
    label="Player model drain: the finder landing's state (X37)")
"""The anchor's and the touch's pointer to the finder landing's state (each
hook lands its own copy of ``drain.c``): its VA; 0 in the finder's own."""
DRAIN_STATE = "_player_model_drain_state"
DRAIN_LIGHT_AT = BytesParam(
    name="drain_light_at", symbol="_player_model_drain_light_at", size=4,
    label="Player model drain: X18's drain slot (X37)")
"""X18's :data:`LIGHT_DRAIN`: its VA, four bytes, so the drain's hit stuns
where the player's own in the column playing does (Step 4.3, D1045); 0 on a
build without X18."""
DRAIN_FX_SIZE = 32
"""The bytes param :data:`DRAIN_FX` holds: a key and its NUL."""
DRAIN_FX = BytesParam(
    name="drain_fx", symbol="_player_model_drain_fx", size=DRAIN_FX_SIZE,
    label="Player model drain: the stream each drain hit plays on its victim (X37)")
"""The key of the graph X37's touch plays (``critter_play_fx``) on each
critter a drain hit takes life from (:data:`DRAIN_STREAM`; zeros: none)."""
DRAIN_STREAM = "fx/damage/v/fx_drain"
"""X37's drain stream (AZ-759, Step 2.196, D764: "can you have some visual
particles coming from the enemy into the player to indicate their life
was drained?"): the key the build appends it under to ``fx.xbr``."""
DRAIN_STREAM_DONOR = "characters/balthazar_airship/fx/fx_default"
"""Whose drain stream it takes: NPC Balthazar's (his [44] pEmitterShape1
under [40] onPlayer, inherit mode 7, on the player he drains, feeding
[2] pSystemShape1, drawn by [0] pRendererB1 and pulled by [8]
pGravityShape1 and [10] pBoxSinkShape1 into his own m_lifedrain)."""
DRAIN_STREAM_GRAFTS = (
    {"from": {"archive": "characters", "key": DRAIN_STREAM_DONOR, "records": [40]}, "parent": fx_edit.ROOT},
    {"from": {"archive": "characters", "key": DRAIN_STREAM_DONOR, "records": [0, 1, 2, 3, 4, 7, 8, 9, 10, 41, 43, 44]},
     "parent": 6})
"""Its grafts on :data:`HIT_FLASH_SOURCE`'s copy (records 0-5: effectOrigin,
m_hitLocation, the timer, the flash and its shape, the unload): [6] the
mode-7 node onPlayer, a root (inherit 7 places it at the game's player:
X37's anchor leaves another graph's node to the game), then [7]-[18] his
stream's renderer, pool, sinks, gravity, emitter and timer, under [6]
(each parent before its child, so the edit below hangs the emitter on the
victim; the pool stays under [6], in the player's frame as his own pool
is in his, so a victim that walks or turns doesn't drag the stream's end
off the chest)."""
DRAIN_STREAM_PULL = 300.0
"""[13] pGravityShape1's magnitude (his 50): a particle at d m is pulled
at 300 / d m/s/s (0xDC010: mag (G - P) / |G - P|^2), so it reaches the
chest from 4 m in about 0.3 s, from 10 m in about 0.7 s and from 16 m in
about 1.15 s (d x sqrt(pi / 2 mag) from rest), inside its 1.3 s life,
at about 37 m/s from 10 m (1.2 m a 1/30 s step), so the 1.6 x 1.6 x 2.2 m
box sink round the chest takes it there: Step 2.196's sitting at 450 and
a 1 x 1 x 1.4 m box saw the pull's near-singular kick fling some 11 m
past him."""
DRAIN_STREAM_SINK = (1.6, 1.6, 2.2)
"""[14] pBoxSink1's scale (its pBoxSink a unit box): the box sink round the
chest, m.  X37 makes it taller by what a clip lifts the player, its
bottom kept at the standing chest's (Step 2.202): as beamlord's jump
attack raised the pull 0.5-0.6 m a tick, particles flying at 20-50 m/s
at the chest it left passed under the lifted box and the pull flung them
12-17 m off the stream's line."""
DRAIN_STREAM_RED = [[0.0, 0.0, 0.0], [0.03, 0.0, 0.0], [0.55, 0.06, 0.04], [1.0, 0.25, 0.18], [1.0, 0.75, 0.65]]
"""His drain texture's (surf 100, a fuzzy cyan ball on black) luminance
ramp: black stays black (blend 5 adds nothing there), the ball red with a
pink-white core."""


def drain_stream_edits(chest: float) -> list[dict]:
    """:data:`DRAIN_STREAM`'s edits on its grafted copy, the chest ``chest``
    m over the player's model origin: the hit's timer (stopped at 2.2 s)
    turns the emitter off from 0.19 s to 0.67 s of clip (its flash's fade
    curve, at half speed) and unloads it at 2.0 s (its unload step, at
    1/6); the emitter hangs on the victim (its hit location), the pool
    under onPlayer (the player's frame) and the pull and the box sink at
    his chest there; red, additive, 0.3 m sprites shrinking to 0.12 m over their
    1.3 s life."""
    if not math.isfinite(chest):
        raise ValueError(f"X37's stream: the chest {chest!r} is not a finite height")
    return [
        {"record": 2, "name": "NormalHit_timer", "type": "timer", "set": {"stopTime": 2.2},
         "links": [{"index": 3, "dst": 18, "dst_plug": "enable", "weight": 0.5}, {"index": 4, "weight": 1 / 6}]},
        {"record": 7, "name": "pRendererB1", "type": "pRendererB",
         "set": {"blendMode": 5.0, "color1R": 1.0, "color1G": 0.6, "color1B": 0.55, "color2R": 0.95, "color2G": 0.15,
                 "color2B": 0.12, "colorAge2": 0.5, "alpha1": 1.0, "alpha2": 0.7, "alphaAge2": 1.3, "size1": 0.3,
                 "size2": 0.12, "sizeAge2": 1.3},
         "texture": {"recolor": {"ramp": DRAIN_STREAM_RED}}},
        {"record": 8, "name": "pSystem1", "type": "transform",
         "set": {"translateY": 0.0, "translateZ": 0.0, "scaleX": 1.0, "scaleY": 1.0, "scaleZ": 1.0}},
        {"record": 11, "name": "pSinkShape1", "type": "pSink", "set": {"maxAge": 1.3}},
        {"record": 12, "name": "pGravity1", "type": "transform", "set": {"translateZ": chest}},
        {"record": 13, "name": "pGravityShape1", "type": "pGravity", "set": {"magnitude": DRAIN_STREAM_PULL}},
        {"record": 14, "name": "pBoxSink1", "type": "transform",
         "set": {"translateZ": chest, **dict(zip(("scaleX", "scaleY", "scaleZ"), DRAIN_STREAM_SINK))}},
        {"record": 16, "name": "pEmitter1", "type": "transform", "parent": 1, "set": {"translateZ": 0.0}},
    ]


def drain_stream(fx_xbr: bytes, characters_xbr: bytes, xbe: bytes, chest: float, base: int | None = None
                 ) -> list[NewResource]:
    """X37's drain stream (AZ-759, Step 2.196, D764): vanilla ``fx_xbr``'s
    :data:`HIT_FLASH_SOURCE` (the plain hit's flash, its timer and its
    unload) copied under :data:`DRAIN_STREAM` with NPC Balthazar's drain
    stream grafted from vanilla ``characters_xbr``
    (:data:`DRAIN_STREAM_GRAFTS`) and :func:`drain_stream_edits`, so,
    played on a critter, it streams red particles from that critter's hit
    location into the chest of the player for 0.67 s and unloads at 2.0 s;
    the entries to append to ``fx.xbr``, numbered from ``base`` (its
    count)."""
    clone = fx_edit.Clone(fx_xbr, HIT_FLASH_SOURCE, xbe, archive="fx", base=base, characters_xbr=characters_xbr)
    clone.apply(drain_stream_edits(chest), DRAIN_STREAM_GRAFTS)
    return clone.build(DRAIN_STREAM)


DRAIN_HOOKS = tuple(TrampolinePatch(
    name=f"{DRAIN_SHIM_NAME}_{what}",
    label=f"Player model drain: {why} (X37) at VA 0x{va:X}",
    va=va,
    replaced_bytes=bytes.fromhex(replaced),
    shim_object=DRAIN_SHIM.object_path(DRAIN_SHIM_NAME, CHECKOUT),
    shim_symbol=f"_c_player_model_drain_{what}",
    float_params=(DRAIN_COLUMNS, DRAIN_SHARE_PARAM, DRAIN_RANGE_PARAM, DRAIN_EVERY, DRAIN_CHEST, DRAIN_BONES,
                  DRAIN_FEET, DRAIN_DRAWN, DRAIN_SINK, DRAIN_BEAMS, DRAIN_AIM_REACH, DRAIN_AIM_CHEST, DRAIN_AIM_HALF),
    bytes_params=(DRAIN_RADIUS_AT, DRAIN_STATE_AT, DRAIN_FX, DRAIN_AIM, DRAIN_LIGHT_AT),
) for what, why, va, replaced in (
    ("find", "the target finder's candidate kept", 0x7EE3B, "8b9668010000"),       # mov edx, [esi+0x168]
    ("anchor", "the worn drain placed on its target", 0x68A49, "8bb0c0000000"),     # mov esi, [eax+0xc0]
    ("touch", "the drain never hits its wearer and heals him", 0x7A1CA, "50ff97b4000000")))   # push eax; call [edi+0xb4]
"""X37's landings, the finder's first (its state the others'): inside
attack_target_find (0x7EBB0) where it records a better candidate (Europe
0x7EDEB), transform_world's inherit mode 7 load of the player critter at
0x68A49 (Europe 0x689F9) and the platform's hit send at 0x7A1CA (Europe
0x7A17A: the push of the hit and the CALL through the toucher's vtable +0xB4)."""


def drain_columns(columns: list[str], picks: list[str], drains) -> int:
    """X37's columns: those (but the roll) whose pick is one of
    ``drains`` (:func:`self_drains`' clips: Balthazar's attack_2)."""
    return sum(1 << i for i, (col, pick) in enumerate(zip(columns, picks)) if col != ROLL and pick in drains)


def beam_columns(characters: bytes, body: Body, columns: list[str], picks: list[str]) -> int:
    """The columns (bit i, the roll left out) whose pick on ``body`` keys
    :data:`~azurik_mod.patches._player_weapons.CAST_SWITCH` above 0, so
    switches Balthazar's lightning on (his attack_3, the beam; a cast
    creature's every attack): X37's aim (AZ-769) and the ranged finisher
    (:func:`ranged_finisher`) read them."""
    mark = {i for i, name in enumerate(body.markers) if name.casefold() == CAST_SWITCH.casefold()}
    if not mark:
        return 0
    toc = parse_toc(characters)
    by_name = {n.casefold(): i for i, n in named_resources(characters).items()}
    out = 0
    for i, (col, pick) in enumerate(zip(columns, picks)):
        at = by_name.get(f"characters/{body.name}/{pick}".casefold())
        if col != ROLL and at is not None and toc[at].tag == "banm" and _keys(read_clip(
                characters, toc[at].file_offset), mark):
            out |= 1 << i
    return out


def cast_plays(picks: list[str], copies: dict[str, str], clips: list[str], cast: tuple[str, ...]) -> list[str]:
    """What each ``attacks_anims`` column plays where W34 keyed a
    creature's ``cast`` (:attr:`_Dressed.cast`), for :func:`beam_columns`:
    a pick's copy the cast keyed (Step 2.204: a body with no attack clip's
    :data:`CAST_DIR` copy), on a clipless body (no ``picks``) the ``g4/``
    timer X12 resolves its Anim ``clips`` to, else the pick itself."""
    if not picks:
        return [BAKED_DIR + c if BAKED_DIR + c in cast else c for c in clips]
    return [copies[p] if copies.get(p) in cast else p for p in picks]


def aim_records(edits) -> tuple[int, ...]:
    """The records of :data:`BEAM_AIM` that ``edits`` (a recipe's fx edits,
    the player's clone's) make inherit mode 7, in record order."""
    return tuple(sorted(e["record"] for e in edits or () if e.get("name") in BEAM_AIM and e.get("inherit") == 7))


def install_drain_shim(xbe: bytearray, columns: int, radius: int, every: bool, stream: str,
                       rig: tuple[float, int, float, float],
                       aim: tuple[int, tuple[int, ...], float, float, float] = (0, (), 0.0, 0.0, 0.0),
                       light_at: int = 0) -> None:
    """Install X37 (``player_model/drain.c``) at VAs 0x7EE3B, 0x68A49 and
    0x7A1CA in ``xbe`` (either release): while the player swings a column
    of ``columns`` (a mask), the drain's mode-7 nodes (its stream and its
    norm_2 box) sit on the critter attack_target_find returns within
    :data:`DRAIN_RANGE`, nearest the swing's yaw at any bearing (X21's
    radius at ``radius``, a VA, raised for that call), picked again while
    the window holds no live one, else on the player; a norm platform's
    touch by the player is dropped while the drain plays and 0.5 s after;
    the target's sends (a common AI critter's first in the window through
    a no-hit window of up to 3.5 s), and the player gains
    :data:`DRAIN_SHARE` of what it lost; another critter's is dropped
    (AZ-758, D765), or with ``every`` (:data:`DRAIN_TARGETS`' ``all``)
    sent as the target's; each sent hit that took life from a critter, a
    killing one too, plays ``stream`` (a graph key, :data:`DRAIN_STREAM`;
    empty: none) on it, its handle then let go by a detach (AZ-759, D764),
    whose pull the anchor puts at ``rig``'s chest (m over the model
    origin) raised by what a clip lifts the body: its lowest of ``rig``'s
    bones posed over the bind pose's lowest (model units), times its drawn
    scale (AZ-764), and whose box sink it makes span the standing chest to
    the lifted one (:data:`DRAIN_STREAM_SINK`, Step 2.202) (:func:`_install`); with ``aim`` (the beam's
    columns, a mask; its bolt targets' records, :func:`aim_records`; its
    reach, its box's half-width and its height straight ahead, m) the
    beam's bolts go on its target's chest while it plays, a critter in its
    box, else straight ahead to its reach (AZ-769); with ``light_at`` (X18's
    :data:`LIGHT_DRAIN`, a VA; installed before it) the drain's hit stuns
    where the player's own in the column playing does, then holds off its
    critter for the rest of the window (Step 4.3, D1045).
    :class:`ValueError` for a key its slot can't hold or a rig or aim value
    that isn't finite (D35)."""
    chest, bones, feet, drawn = rig
    beams, records, reach, half, height = aim
    if not all(math.isfinite(v) for v in (chest, feet, drawn, reach, half, height)):
        raise ValueError(f"X37: the drain stream's rig {rig!r} or the beam's aim {aim!r} isn't finite")
    if len(records) > DRAIN_AIM.size - 1 or any(not 0 <= r < 256 for r in records):
        raise ValueError(f"X37: the beam's bolt targets {records!r} don't fit its {DRAIN_AIM.size}-byte slot")
    raw = stream.encode("ascii")
    if len(raw) >= DRAIN_FX_SIZE:
        raise ValueError(f"X37: the drain stream's key {stream!r} doesn't fit its {DRAIN_FX_SIZE}-byte slot")
    params = {DRAIN_COLUMNS.name: float(columns), DRAIN_SHARE_PARAM.name: DRAIN_SHARE,
              DRAIN_RANGE_PARAM.name: DRAIN_RANGE, DRAIN_EVERY.name: float(every),
              DRAIN_CHEST.name: float(chest) if stream else 0.0, DRAIN_BONES.name: float(bones),
              DRAIN_FEET.name: float(feet), DRAIN_DRAWN.name: float(drawn),
              DRAIN_SINK.name: DRAIN_STREAM_SINK[2] if stream else 0.0,
              DRAIN_BEAMS.name: float(beams) if records else 0.0, DRAIN_AIM_REACH.name: float(reach),
              DRAIN_AIM_CHEST.name: float(height), DRAIN_AIM_HALF.name: float(half),
              DRAIN_AIM.name: bytes([len(records), *records]).ljust(DRAIN_AIM.size, b"\0"),
              DRAIN_RADIUS_AT.name: struct.pack("<I", radius), DRAIN_FX.name: raw + bytes(DRAIN_FX_SIZE - len(raw)),
              DRAIN_LIGHT_AT.name: struct.pack("<I", light_at)}
    find, *rest = DRAIN_HOOKS
    _install(xbe, find, DRAIN_SHIM, "drain", params)
    state = trampoline_symbol_va(xbe, find, DRAIN_STATE, CHECKOUT, shim_source=DRAIN_SHIM.source_path())
    for hook in rest:
        _install(xbe, hook, DRAIN_SHIM, "drain", params | {DRAIN_STATE_AT.name: struct.pack("<I", state)})
# --- X38: a worn body's ranged attack effects in their own instances (Step 2.149, D429, D430) ---
FX_RING_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="fx_ring")
FX_RING_SHIM_NAME = "player_model_fx_ring"
"""Its object's name: ``player_model_fx_ring.o`` in the shim build dir."""
FX_RING_TABLE = BytesParam(name="fx_ring_table", symbol="_player_model_fx_ring_table", size=fx_ring.TABLE_SIZE,
                           label="Player model ranged effects: the ring's table (X38)")
"""The build's table (:meth:`~azurik_mod.patches._player_fx_ring.Plan.pack`), in each of the three landings."""
FX_RING_AT = BytesParam(name="fx_ring_at", symbol="_player_model_fx_ring_at", size=4,
                        label="Player model ranged effects: the spawn landing's ring (X38)")
"""The tick and hit landings' pointer to the spawn landing's ring (:data:`FX_RING_STATE`); 0 in the spawn's own."""
FX_ROTATION_AT = BytesParam(name="fx_rotation_at", symbol="_player_model_fx_rotation_at", size=4,
                            label="Player model ranged effects: X10's ring (X38)")
"""X10's ring's VA when the build has one (a rotating column's row is the entry it played), else 0."""
FX_DRAIN_AT = BytesParam(name="fx_ring_drain_at", symbol="_player_model_fx_ring_drain_at", size=4,
                         label="Player model ranged effects: X37's state (X38)")
"""X37's state's VA (:data:`DRAIN_STATE`) when the build has X37, else 0: a drain row's detached copy goes into its
held list, so X37 keeps the copy's mode-7 nodes on the drain's target (AZ-653, Step 2.153c)."""
FX_RING_STATE = "_player_model_fx_ring_state"
"""The ring's symbol in the spawn landing's .bss."""
FX_RING_HOOKS = tuple(TrampolinePatch(
    name=f"{FX_RING_SHIM_NAME}_{what}",
    label=f"Player model ranged effects: {why} (X38) at VA 0x{va:X}",
    va=va,
    replaced_bytes=_call(va, target),
    shim_object=FX_RING_SHIM.object_path(FX_RING_SHIM_NAME, CHECKOUT),
    shim_symbol=f"_c_player_model_fx_ring_{what}",
    bytes_params=(FX_RING_TABLE, FX_RING_AT, FX_ROTATION_AT, FX_DRAIN_AT),
) for what, why, va, target in (
    ("spawn", "an attack's copies spawned and armed", 0x88A5E, 0x4FF10),
    ("tick", "each copy detached, played out and ended", 0x43A62, 0xCBC80),
    ("hit", "a hit's clip change", 0x8D6AF, 0x44640)))
"""X38's landings, one object each, the spawn's first (its ring the others
reach): player_attack_enter's (0x88990) CALL of quat_from_euler
(0x4FF10) at 0x88A5E, after its clip change and rate, on every attack
entry (Europe 0x88A0E); the anim step's (0x43A00, ESI the critter)
CALL of anim_sample_markers (0xCBC80) at 0x43A62, once a critter tick
(Europe 0x43A62, its CALL 0xCBE00); and the player hit handler's
(0x8D600, ESI the PlayerControl) CALL of apply_damage (0x44640) at
0x8D6AF, after X7's reaction change (Europe 0x8D65F; AZ-650, Step 2.155)."""


def install_fx_ring_shim(xbe: bytearray, plan: fx_ring.Plan, rotation_at: int = 0, drain_at: int = 0) -> None:
    """Install X38 (``player_model/fx_ring.c``) at VAs 0x88A5E, 0x43A62 and
    0x8D6AF in ``xbe`` (either release), one landing each, the others with
    the spawn landing's ring: each attack whose row ``plan`` gives a copy
    spawns its own instance of the body's graph bound to the player's
    markers (a P key's resting one armed instead), the next clip change
    (a hit's before the tick's re-samples, AZ-650) detaches it, and it
    plays out its windows where it is and ends; the own instance's
    emitters a copy shows are off while it shows them
    (:mod:`~azurik_mod.patches._player_fx_ring`, :func:`_install`).
    ``rotation_at`` is X10's ring's VA (0: none), ``drain_at`` X37's
    state's (0: none; a drain row's detached copy goes into its held
    list, AZ-653).  :class:`ValueError` when the table doesn't fit (D35)."""
    params = {FX_RING_TABLE.name: plan.pack(), FX_ROTATION_AT.name: struct.pack("<I", rotation_at),
              FX_DRAIN_AT.name: struct.pack("<I", drain_at)}
    spawn, *rest = FX_RING_HOOKS
    _install(xbe, spawn, FX_RING_SHIM, "fx ring", params)
    ring = trampoline_symbol_va(xbe, spawn, FX_RING_STATE, CHECKOUT, shim_source=FX_RING_SHIM.source_path())
    for hook in rest:
        _install(xbe, hook, FX_RING_SHIM, "fx ring", params | {FX_RING_AT.name: struct.pack("<I", ring)})


# --- X40: the player's default fx is the build's clone (Step 2.157, D446) ---
FX_DEFAULT_HOOK_VA = 0x43719
"""0x43700's (a body's default fx, run by the critter init for every
critter) ``push 0x19FD34``, the format 'characters/%s/fx/fx_default'
(Europe ``push 0x1A1EEC`` at the same VA), which X40 replaces."""
FX_DEFAULT_FORMAT_VA = 0x19FD34
_FX_DEFAULT_VANILLA = b"\x68" + struct.pack("<I", FX_DEFAULT_FORMAT_VA)
FX_DEFAULT_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="fx_default")
FX_DEFAULT_SHIM_NAME = "player_model_fx_default"
"""Its object's name: ``player_model_fx_default.o`` in the shim build dir."""
FX_DEFAULT_HOOK = TrampolinePatch(
    name=FX_DEFAULT_SHIM_NAME,
    label=f"Player model fx: the player's clone of the body's default fx (X40) at VA 0x{FX_DEFAULT_HOOK_VA:X}",
    va=FX_DEFAULT_HOOK_VA,
    replaced_bytes=_FX_DEFAULT_VANILLA,
    shim_object=FX_DEFAULT_SHIM.object_path(FX_DEFAULT_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_fx_default",
)


def player_fx_key(characters: bytes, body: str) -> str:
    """The key of the default fx the player's critter of ``body`` plays in
    a build whose characters.xbr is ``characters``: the build's clone
    (:func:`~azurik_mod.assets.fx_edit.clone_key`, which X40 binds) when
    the archive names it, else the body's own (lower case)."""
    clone = fx_edit.clone_key(body)
    return clone if any(n.casefold() == clone for n in named_resources(characters).values()) else (
        fx_edit.default_key(body))


def install_fx_default_shim(xbe: bytearray, characters: bytes, index_xbr: bytes, body: str) -> None:
    """Install X40 (``player_model/fx_default.c``) at VA 0x43719 in ``xbe``
    (either release): the player's species (its ai class 'player''s,
    ``player_ai_factory``) formats ``characters/<body>/v/fx/fx_default``,
    every other critter the vanilla key.  Refused (D35) unless the build's
    ``characters`` names that key and ``index_xbr`` holds its record: the
    player would load no default fx (:func:`_install`)."""
    key = fx_edit.clone_key(body)
    if player_fx_key(characters, body) != key or not any(
            r.key.casefold() == key for r in parse_index_xbr(index_xbr).records):
        raise ValueError(f"X40: the build doesn't add {key} to characters.xbr and index.xbr, so the player would "
                         "load no default fx")
    _install(xbe, FX_DEFAULT_HOOK, FX_DEFAULT_SHIM, "fx-default")


# --- X47: the player binds its own recoloured copy of its body (Step 2.170b; D539, D734) ---
BODY_KEY_HOOK_VA = 0x4B900
"""The species bind's (0x4B8E0, once per species) ``push 0x19F270``, the
format 'characters/%s' (Europe ``push 0x1A1428`` at the same VA), which
X47 replaces."""
BODY_KEY_FORMAT_VA = 0x19F270
BODY_KEY_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="body_key")
BODY_KEY_SHIM_NAME = "player_model_body_key"
"""Its object's name: ``player_model_body_key.o`` in the shim build dir."""
BODY_KEY_HOOK = TrampolinePatch(
    name=BODY_KEY_SHIM_NAME,
    label=f"Player model body: the player's recoloured copy of its body (X47) at VA 0x{BODY_KEY_HOOK_VA:X}",
    va=BODY_KEY_HOOK_VA,
    replaced_bytes=b"\x68" + struct.pack("<I", BODY_KEY_FORMAT_VA),
    shim_object=BODY_KEY_SHIM.object_path(BODY_KEY_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_body_key",
)


def install_body_key_shim(xbe: bytearray, characters: bytes, index_xbr: bytes, body: str) -> None:
    """Install X47 (``player_model/body_key.c``) at VA 0x4B900 in ``xbe``
    (either release): the player's species (the ``player`` flag 0x20 in
    its +0x64) binds ``characters/<body>/v/skin``, W38's copy, every other
    species the vanilla key.  Refused (D35) unless ``characters`` names
    that key and ``index_xbr`` holds its record: the player would bind no
    body (:func:`_install`)."""
    key = skin_key(body)
    if not any(n.casefold() == key for n in named_resources(characters).values()) or not any(
            r.key.casefold() == key for r in parse_index_xbr(index_xbr).records):
        raise ValueError(f"X47: the build doesn't add {key} to characters.xbr and index.xbr, so the player would "
                         "bind no body")
    _install(xbe, BODY_KEY_HOOK, BODY_KEY_SHIM, "body-key")

# --- X41: a worn body's jiggle bones on real-time springs (Step 2.156; D443, D444, D445) ---
JIGGLE_HOOK_VA = 0xCB5CB
"""The pose's matrix builder's (0xCB550) per-bone CALL of anim_bone_matrix
(0xCA470), which X41 replaces (Europe 0xCB74B -> 0xCA5F0); the root
path's JMP at 0xCB5A4 lands on it, so a CALL for a CALL keeps it an
instruction start."""
JIGGLE_SCENE_LOAD_VA = 0x513D3
JIGGLE_SCENE_LOAD = bytes.fromhex("8b0d") + struct.pack("<I", 0x1BF63C)
"""``mov ecx, [scene]`` (USA's bytes): the build reads the scene global's
address (USA 0x1BF63C, Europe 0x1C15DC) from this load in its own image."""
JIGGLE_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="jiggle")
JIGGLE_SHIM_NAME = "player_model_jiggle"
"""Its object's name: ``player_model_jiggle.o`` in the shim build dir."""
JIGGLE_TABLE = BytesParam(name="jiggle_bones", symbol="_player_model_jiggle_bones", size=jiggle_rt.TABLE_SIZE,
                          label="Player model jiggle: the spring rows (X41)")
"""The build's spring rows (:func:`~azurik_mod.assets.jiggle_rt.table`)."""
JIGGLE_SCENE = BytesParam(name="jiggle_scene", symbol="_player_model_jiggle_scene", size=4,
                          label="Player model jiggle: the scene global (X41)")
JIGGLE_X26 = BytesParam(name="jiggle_x26", symbol="_player_model_jiggle_x26", size=8,
                        label="Player model jiggle: X26's latch words (X41)")
"""X26's ``player_model_stance_held`` and ``_edge`` VAs (0, 0 without
X26): X41 puts them back after its own 0x42200 call."""
JIGGLE_STRENGTH = FloatParam(
    name="jiggle_strength", symbol="_player_model_jiggle_strength", default=1.0,
    label="Player model jiggle strength (X41)",
    description="How far the jiggle bones swing, times their recipe's: 0 rigid (X41 isn't installed), 1 the "
                "recipe's, 2 twice as far, negative mirrored; any finite number.")
JIGGLE_HOOK = TrampolinePatch(
    name=JIGGLE_SHIM_NAME,
    label=f"Player model jiggle: real-time springs on the worn body's jiggle bones (X41) at VA 0x{JIGGLE_HOOK_VA:X}",
    va=JIGGLE_HOOK_VA,
    replaced_bytes=_call(JIGGLE_HOOK_VA, 0xCA470),
    shim_object=JIGGLE_SHIM.object_path(JIGGLE_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_jiggle",
    float_params=(JIGGLE_STRENGTH,),
    bytes_params=(JIGGLE_TABLE, JIGGLE_SCENE, JIGGLE_X26),
)
JIGGLE_WORDS = ("_player_model_jiggle_build", "_player_model_jiggle_steps", "_player_model_jiggle_resets",
                "_player_model_jiggle_m", "_player_model_jiggle_shown", "_player_model_jiggle_state")
"""The words X41 exports (its .bss), for L2 and the sitting."""


def install_jiggle_shim(xbe: bytearray, table: bytes, strength: float = 1.0, x26: tuple[int, int] = (0, 0)) -> None:
    """Install X41 (``player_model/jiggle.c``) at VA 0xCB5CB in ``xbe``
    (either release) with ``table``'s spring rows
    (:func:`~azurik_mod.assets.jiggle_rt.table`), the strength slider and
    X26's latch words (``x26``, their VAs; 0 without X26): the player's
    jiggle bones swing on springs driven by its drawn motion, every other
    critter's bones are the game's (:func:`_install`).  The scene global
    comes from the image's own load at 0x513D3.  :class:`ValueError`
    names a load that isn't ``mov ecx, [disp32]`` (D35)."""
    _, at, load = xbe_site(xbe, JIGGLE_SCENE_LOAD_VA, JIGGLE_SCENE_LOAD)
    if bytes(xbe[at:at + 6]) != load:
        raise ValueError(f"the jiggle shim: VA 0x{JIGGLE_SCENE_LOAD_VA:X} isn't the scene global's load")
    _install(xbe, JIGGLE_HOOK, JIGGLE_SHIM, "jiggle", {
        JIGGLE_TABLE.name: table, JIGGLE_SCENE.name: load[2:6],
        JIGGLE_X26.name: struct.pack("<II", *x26), JIGGLE_STRENGTH.name: strength})


# --- X39: a variant's air blast holds its bolt in the air and blasts where the body lands (Steps 2.153, 2.153b) ---
BLAST_HOOK_VA = 0x8D44D
"""The attack state's chain check's CALL of anim_layer_fraction (0xCB020)
at 0x8D44D (Europe 0x8D3FD), ECX the anim object, in state 0x100 only:
X39 takes it."""
BLAST_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="air_blast")
BLAST_SHIM_NAME = "player_model_air_blast"
"""Its object's name: ``player_model_air_blast.o`` in the shim build dir."""
BLAST_COLUMNS = FloatParam(
    name="blast_columns", symbol="_player_model_blast_columns", default=0.0,
    label="Player model air blast columns (X39)",
    description="The attacks_anims columns (a 24-bit mask) whose clip is an air blast: on the first ground tick "
                "after a landing its clip jumps to the impact.")
BLAST_IMPACT = FloatParam(
    name="blast_impact", symbol="_player_model_blast_impact", default=0.0,
    label="Player model air blast impact (X39)",
    description="The clip time, s, the air blast's clip jumps to (never back) when the body lands: its blast's start.")
BLAST_HOOK = TrampolinePatch(
    name=BLAST_SHIM_NAME,
    label=f"Player model air blast: its impact when the body lands (X39) at VA 0x{BLAST_HOOK_VA:X}",
    va=BLAST_HOOK_VA,
    replaced_bytes=_call(BLAST_HOOK_VA, 0xCB020),
    shim_object=BLAST_SHIM.object_path(BLAST_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_air_blast",
    float_params=(BLAST_COLUMNS, BLAST_IMPACT),
)
BLAST_HOLD_HOOK = TrampolinePatch(
    name=f"{BLAST_SHIM_NAME}_hold",
    label="Player model air blast: its bolt held while airborne (X39) at VA 0x8D39A",
    va=0x8D39A,
    replaced_bytes=_call(0x8D39A, 0x89480),
    shim_object=BLAST_SHIM.object_path(BLAST_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_air_blast_hold",
    float_params=(BLAST_COLUMNS, BLAST_IMPACT),
)
"""The state machine's CALL of player_airborne_tick (0x89480) at 0x8D39A,
every airborne tick of the air attack's state 0x102 (Europe 0x8D34A,
callee 0x89430): X39 holds the blast clip short of its impact there."""
BLAST_LAND_HOOKS = tuple(TrampolinePatch(
    name=f"{BLAST_SHIM_NAME}_land{k}",
    label=f"Player model air blast: a hard landing lands soft in its column (X39) at VA 0x{va:X}",
    va=va,
    replaced_bytes=_call(va, 0x8B100),
    shim_object=BLAST_SHIM.object_path(BLAST_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_air_blast_land",
    float_params=(BLAST_COLUMNS, BLAST_IMPACT),
) for k, va in enumerate((0x85A7C, 0x85B65), 1))
"""player_land_classify's two CALLs of the hard landing player_hard_land
(0x8B100) at 0x85A7C and 0x85B65 (Europe 0x85A2C and 0x85B15, callee
0x8B0B0), each followed by the classifier's epilogue alone."""
BLAST_HOOKS = (BLAST_HOOK, BLAST_HOLD_HOOK, *BLAST_LAND_HOOKS)
"""X39's four landings, in install order."""


def install_air_blast_shim(xbe: bytearray, columns: int, impact: float) -> None:
    """Install X39 (``player_model/air_blast.c``) in ``xbe`` (either
    release), one landing per hook (:data:`BLAST_HOOKS`), each with
    ``columns`` (a mask) and ``impact`` (clip s), for a column of
    ``columns`` whose slot still plays: at VA 0x8D39A, while airborne in
    the air attack's state, the clip's time is held short of ``impact``,
    so the bolt fires until he lands; at 0x85A7C and 0x85B65 a hard
    landing in that state lands soft (no touchdown); and at 0x8D44D, on
    the first ground-attack tick after the landing, the clip's time goes
    to ``impact`` if it is short of it, so the blast plays where he
    landed; every other tick is the game's (:func:`_install`)."""
    params = {BLAST_COLUMNS.name: float(columns), BLAST_IMPACT.name: float(impact)}
    for hook in BLAST_HOOKS:
        _install(xbe, hook, BLAST_SHIM, "air-blast", params)


# --- X49: a recipe's seeking columns turn to their target at the attack's start (Step 2.194b, D761, D762) ---
SEEK_HOOK_VA = 0x88A3A
"""``player_attack_enter``'s (0x88990) load of the swing's yaw, ``mov eax,
[edi+0x138]`` (Europe 0x889EA, the same instruction), after its clip
change (0x889A6) and before ``quat_from_euler`` (0x88A5E) makes the yaw
the turn the attack's first tick gives the body; X49 takes it."""
SEEK_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="seek")
SEEK_SHIM_NAME = "player_model_seek"
"""Its object's name: ``player_model_seek.o`` in the shim build dir."""
SEEK_COLUMNS = FloatParam(
    name="seek_columns", symbol="_player_model_seek_columns", default=0.0,
    label="Player model seeking columns (X49)",
    description="The attacks_anims columns (bit i: column i) that turn to their target at the attack's start.")
SEEK_RANGE = FloatParam(
    name="seek_range", symbol="_player_model_seek_range", default=14.0,
    label="Player model seek range (X49)",
    description="How far, in metres (distance less radius), a seeking column looks for its target.")
SEEK_CONE = FloatParam(
    name="seek_cone", symbol="_player_model_seek_cone", default=45.0,
    label="Player model seek cone (X49)",
    description="How many degrees either side of the attack's heading a seeking column takes its target.")
SEEK_RADIUS_AT = BytesParam(
    name="seek_radius_at", symbol="_player_model_seek_radius_at", size=4,
    label="Player model seek: X21's search radius (X49)")
"""X21's writable radius (:data:`SEARCH_RADIUS_SYMBOL`): its VA, four bytes."""
SEEK_HOOK = TrampolinePatch(
    name=SEEK_SHIM_NAME,
    label=f"Player model seek: a seeking column turns to its target (X49) at VA 0x{SEEK_HOOK_VA:X}",
    va=SEEK_HOOK_VA,
    replaced_bytes=bytes.fromhex("8b8738010000"),   # mov eax, [edi+0x138]
    shim_object=SEEK_SHIM.object_path(SEEK_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_seek",
    float_params=(SEEK_COLUMNS, SEEK_RANGE, SEEK_CONE),
    bytes_params=(SEEK_RADIUS_AT,),
)


def install_seek_shim(xbe: bytearray, columns: int, radius: int) -> None:
    """Install X49 (``player_model/seek.c``) at VA 0x88A3A in ``xbe``
    (either release): an attack of ``columns`` (a mask) whose own slot
    plays turns, from its first tick, to the critter attack_target_find
    gives within the kit throw's range and cone (``kit.json``'s 14 m and
    45 degrees, D762: "the same cone and radius") of its heading (X21's
    radius at ``radius``, a VA, raised for the call): its yaw is that
    critter's bearing less the column's Aim, as the game's own target
    bearing is (:func:`_install`)."""
    aim = kit_document()["throw"]
    _install(xbe, SEEK_HOOK, SEEK_SHIM, "seek", {
        SEEK_COLUMNS.name: float(columns), SEEK_RANGE.name: float(aim["range"]), SEEK_CONE.name: float(aim["cone"]),
        SEEK_RADIUS_AT.name: struct.pack("<I", radius)})


# --- X19: the camera keeps its distance from a tall point (Step 2.104) ------
EYE_SWEEP_HOOK_VA = 0x810F3
"""The level camera's (0x80FB0) CALL of collision_sweep (0x60870) from its
point to the wanted camera place, which X19 replaces."""
_EYE_SWEEP_VANILLA = _call(EYE_SWEEP_HOOK_VA, 0x60870)    # CALL collision_sweep
EYE_SWEEP_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="eye_sweep")
EYE_SWEEP_SHIM_NAME = "player_model_eye_sweep"
"""Its object's name: ``player_model_eye_sweep.o`` in the shim build dir."""
EYE_LIFT = FloatParam(
    name="eye_lift", symbol="_player_model_eye_lift", default=0.0,
    label="Player model camera sweep lift (X19)",
    description="How far, in metres, the player's camera point sits above garret4's eye height: "
                "a camera sweep that hits from the point is tried again that much lower.")
EYE_SWEEP_HOOK = TrampolinePatch(
    name=EYE_SWEEP_SHIM_NAME,
    label=f"Player model camera: its distance kept from a tall point (X19) at VA 0x{EYE_SWEEP_HOOK_VA:X}",
    va=EYE_SWEEP_HOOK_VA,
    replaced_bytes=_EYE_SWEEP_VANILLA,
    shim_object=EYE_SWEEP_SHIM.object_path(EYE_SWEEP_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_eye_sweep@36",
    float_params=(EYE_LIFT,),
)
EYE_SIGHT_HOOK_VA = 0x80C35
"""The level camera's line-of-sight test's (0x80C10, called once at 0x81B80)
CALL of collision_sweep from the camera's place to its point, which X19's
second entry replaces (Step 2.107)."""
EYE_SIGHT_HOOK = TrampolinePatch(
    name=f"{EYE_SWEEP_SHIM_NAME}_sight",
    label=f"Player model camera: its line of sight from garret4's eye height (X19) at VA 0x{EYE_SIGHT_HOOK_VA:X}",
    va=EYE_SIGHT_HOOK_VA,
    replaced_bytes=_call(EYE_SIGHT_HOOK_VA, 0x60870),
    shim_object=EYE_SWEEP_SHIM.object_path(EYE_SWEEP_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_eye_sight@36",
    float_params=(EYE_LIFT,),
)


EYE_REGROW_HOOK_VA = 0x819C9
"""The level camera's regrow step's add (0x81952-0x81A04), ``fld dword ptr
[esp+0x1c]; fadd dword ptr [eax+0x19c]`` (10 bytes; 0x819D3 stores the
sum), which X19's third entry replaces (Step 2.116d, B2; Europe
0x81979)."""
SIGHT_RADIUS_AT = BytesParam(
    name="sight_radius_at", symbol="_player_model_sight_radius_at", size=4,
    label="Player model camera regrow: the sight landing's radius (X19)")
"""The regrow landing's pointer to the sight landing's copy of the sweep
radius the game passes the sight test (each hook lands its own copy of
``eye_sweep.c``): its VA, four bytes."""
EYE_REGROW_HOOK = TrampolinePatch(
    name=f"{EYE_SWEEP_SHIM_NAME}_regrow",
    label=f"Player model camera: the regrow waits for garret4's line (X19) at VA 0x{EYE_REGROW_HOOK_VA:X}",
    va=EYE_REGROW_HOOK_VA,
    replaced_bytes=bytes(10),   # fld [esp + 0x1c]; fadd [eax + 0x19c]
    shim_object=EYE_SWEEP_SHIM.object_path(EYE_SWEEP_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_eye_regrow",
    float_params=(EYE_LIFT,),
    bytes_params=(SIGHT_RADIUS_AT,),
)


EYE_LIFT_MIN = 0.01
"""The least lift (m) X19 is installed for: a point at garret4's eye height
(any body sized to his height at x1) computes to a rounding error off it."""


def install_eye_sweep_shim(xbe: bytearray, lift: float, rig: bool = False) -> None:
    """Install X19 (``player_model/eye_sweep.c``) at VAs 0x810F3 and 0x80C35
    in ``xbe``: when the level camera's sweep from the player's point to its
    wanted place hits, it is tried again from ``lift`` m lower on the line
    from the body's centre to the point (never below the centre), and when
    that one is clear the camera keeps its distance; its line-of-sight test
    from its place to the point tries the same lowered point (Step 2.107),
    so the 0.8 s pull-in a blocked sight brings follows garret4's eye
    height; a swimming player, any other target and a clear first sweep
    are the game's.  With X25's ``rig`` also at 0x819C9 (Step 2.116d, B2):
    a pulled-in camera's regrow step waits while the line from the lowered
    point out along the camera's direction to the grown distance is
    blocked, so it regrows when garret4's would (:func:`_install`)."""
    for hook, what in ((EYE_SWEEP_HOOK, "camera sweep"), (EYE_SIGHT_HOOK, "camera sight")):
        _install(xbe, hook, EYE_SWEEP_SHIM, what, {EYE_LIFT.name: lift})
    if rig:
        at = trampoline_symbol_va(xbe, EYE_SIGHT_HOOK, "_player_model_sight_radius", CHECKOUT,
                                  shim_source=EYE_SWEEP_SHIM.source_path())
        _install(xbe, EYE_REGROW_HOOK, EYE_SWEEP_SHIM, "camera regrow",
                 {EYE_LIFT.name: lift, SIGHT_RADIUS_AT.name: struct.pack("<I", at)})


# --- X20: the zipline ride's camera point no lower than the centre (Step 2.105) ---
EYE_HANG_HOOK_VA = 0x81292
"""Where the level camera (0x81240), its point got from its target (the
CALL [EAX+0xB0] at 0x81271 into its local at ESP + 0x50), first goes on:
``mov edi, [esp+0x10]`` and ``mov edx, [edi+0x154]``, which X20 replaces
(10 bytes)."""
_EYE_HANG_VANILLA = bytes(10)
EYE_HANG_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="eye_hang")
EYE_HANG_SHIM_NAME = "player_model_eye_hang"
"""Its object's name: ``player_model_eye_hang.o`` in the shim build dir."""
EYE_HANG_HOOK = TrampolinePatch(
    name=EYE_HANG_SHIM_NAME,
    label=f"Player model camera: the zipline ride's point no lower than the centre (X20) at VA 0x{EYE_HANG_HOOK_VA:X}",
    va=EYE_HANG_HOOK_VA,
    replaced_bytes=_EYE_HANG_VANILLA,
    shim_object=EYE_HANG_SHIM.object_path(EYE_HANG_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_eye_hang",
)


def install_eye_hang_shim(xbe: bytearray) -> None:
    """Install X20 (``player_model/eye_hang.c``) at VA 0x81292 in ``xbe``:
    while the player hangs onto the zipline (hang_start, 0x105; Step
    2.107) or rides it (move state 5), or is airborne (state 2) with its
    drawn origin more than 1.25 m under its centre (X22 easing it off the
    ride), the level camera's point is raised to the body's centre where
    it hangs lower, as a body drawn taller than garret4 does
    (:func:`camera_plan`; X9 hangs it X' times garret4's grab under the
    cable, :func:`hang_scale`); every other state and target keeps the
    game's point (:func:`_install`)."""
    _install(xbe, EYE_HANG_HOOK, EYE_HANG_SHIM, "camera hang")


# --- X21: the combo chains on a stunned target out to its basics' reach (Step 2.105) ---
SEARCH_HOOK_VA = 0x7EF80
"""The attack transition search's (0x7EF10) CALL of its target finder
(attack_target_find, 0x7EBB0), its only caller, which X21 replaces."""
_SEARCH_VANILLA = _call(SEARCH_HOOK_VA, 0x7EBB0)    # CALL attack_target_find
SEARCH_RADIUS = 3.0
"""How far (m, distance less radius) 0x7EBB0 looks for a target: the
constant at 0x1A25BC, shared by 35 instructions."""
SEARCH_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="target_search")
SEARCH_SHIM_NAME = "player_model_target_search"
"""Its object's name: ``player_model_target_search.o`` in the shim build dir."""
SEARCH_REACH = FloatParam(
    name="search_reach", symbol="_player_model_search_reach", default=0.0,
    label="Player model chain search reach (X21)",
    description="How far, in metres, the combo looks for a stunned or frozen target when none is within "
                "3 m: the farthest the build's basic1-3 boxes reach.")
SEARCH_HOOK = TrampolinePatch(
    name=SEARCH_SHIM_NAME,
    label=f"Player model combo: a stunned target out to its basics' reach (X21) at VA 0x{SEARCH_HOOK_VA:X}",
    va=SEARCH_HOOK_VA,
    replaced_bytes=_SEARCH_VANILLA,
    shim_object=SEARCH_SHIM.object_path(SEARCH_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_target_search@12",
    float_params=(SEARCH_REACH,),
)
SEARCH_RADIUS_SYMBOL = "_player_model_search_radius"
"""X21's writable radius (3.0 but while it searches farther), which the
build points :data:`SEARCH_SITES` at."""


@dataclass(frozen=True)
class Site:
    """A vanilla site a plain byte patch of the swap rewrites: its USA VA
    and its vanilla bytes there (X21's reads of :data:`SEARCH_RADIUS`, an
    x87 op on ``[0x1A25BC]``: the opcode, the ModRM and the constant's VA;
    X25's camera constants and its NOP)."""

    va: int
    original: bytes


SEARCH_SITES = tuple(Site(va, bytes.fromhex(op) + struct.pack("<I", 0x1A25BC)) for va, op in (
    (0x7EC10, "d805"), (0x7EC20, "d805"), (0x7EC36, "d805"),     # fadd: the query cube's top
    (0x7EC53, "d825"), (0x7EC5D, "d825"), (0x7EC67, "d825"),     # fsub: its bottom
    (0x7EDA4, "d81d")))                                          # fcomp: distance less radius
"""X21's seven repoints (0x7EBB0's every read of 0x1A25BC; the abs32 at +2)."""


def search_reach(characters_xbr: bytes, body: Body, columns: list[str], picks: list[str], scale: float,
                 x3: int, x3_far: float, rotate: tuple[list[int], int] | None = None,
                 reach: float = 1.0, bump: int = 0, melee: bool = False,
                 chained: tuple[str, ...] | None = None, model_scale: float = 1.0) -> float:
    """X21's reach (Step 2.105, AZ-523): the farthest any box of a build's
    basic1-3 (``chained``: :data:`CHAINED`, and with X36 every column a set
    plays there, Step 2.135) reaches from the feet, in metres, melee or
    not (with ``melee``, a variant's, melee boxes alone: a 14 m beam in
    basic1 would search 14 m out, Step 2.137; :func:`melee_reach`'s rule
    for those columns, its line at ``model_scale``, AZ-567), at least
    :data:`SEARCH_RADIUS`."""
    return max(melee_reach(characters_xbr, body, columns, picks, scale, x3, x3_far, rotate, None, reach, bump,
                           only=chained or CHAINED, melee=melee, model_scale=model_scale) or 0.0, SEARCH_RADIUS)


def install_search_shim(xbe: bytearray, reach: float) -> None:
    """Install X21 (``player_model/target_search.c``) at VA 0x7EF80 in
    ``xbe`` (either release) and point 0x7EBB0's seven reads of its 3.0
    m radius (:data:`SEARCH_SITES`) at the shim's own: when the combo's
    search finds no target within 3 m, the player's in basic1-3
    (:data:`CHAINED`, ``attacks_anims``' columns 0-2, which the shim reads
    by index) searches again out to ``reach`` (:func:`search_reach`) and
    takes a stunned or frozen target there.  A site that doesn't hold its
    vanilla bytes raises :class:`ValueError` before anything is written
    (D27, D35; :func:`_install`)."""
    offs = []
    for site in SEARCH_SITES:
        _, off, vanilla = xbe_site(xbe, site.va, site.original)
        if bytes(xbe[off:off + len(vanilla)]) != vanilla:
            raise ValueError(f"X21: VA 0x{site.va:X} doesn't hold vanilla's read of the 3 m search radius; "
                             "rebuild from vanilla")
        offs.append(off)
    _install(xbe, SEARCH_HOOK, SEARCH_SHIM, "target search", {SEARCH_REACH.name: reach})
    radius = trampoline_symbol_va(xbe, SEARCH_HOOK, SEARCH_RADIUS_SYMBOL, CHECKOUT,
                                  shim_source=SEARCH_SHIM.source_path())
    for off in offs:
        xbe[off + 2:off + 6] = struct.pack("<I", radius)


# --- X22: a body drawn at a model scale eases off the zipline (Step 2.105) ---
HANG_EASE_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="hang_ease")
HANG_EASE_SHIM_NAME = "player_model_hang_ease"
"""Its object's name: ``player_model_hang_ease.o`` in the shim build dir."""
HANG_STEP = FloatParam(
    name="hang_step", symbol="_player_model_hang_step", default=0.847,
    label="Player model hang ease step (X22)",
    description="The most, in metres, the drawn body moves against its centre a placement as it eases "
                "from its hang to its stance: the control's own let-go step.")
HANG_SPAN = FloatParam(
    name="hang_span", symbol="_player_model_hang_span", default=0.0,
    label="Player model hang ease span (X22)",
    description="The farthest, in metres, a new drawn offset may lie from the old one and still be eased "
                "toward: |X - 1| x garret4's hang grab plus 2 m.")
EASE_SHARED = BytesParam(
    name="ease_shared", symbol="_player_model_ease_shared", size=4,
    label="Player model hang ease: the airborne landing's state block (X22)")
"""The address of the airborne landing's state block (:data:`EASE_STATE`:
the last placement's clock time, critter and aligned-node term, Step
2.175b, AZ-600), which the let-go's and the flap's landings read and
write; 0 in the airborne landing (its own block)."""
EASE_STATE = "_player_model_ease_state"
"""The state block's symbol in the airborne landing."""
EASE_INTO = (15, 16, 18, 21)
"""The slots the airborne move plays after the hang (jump, jump_standing:
the let-go's anim change at 0x89254; fall, fall_big: the airborne tick's
at 0x898B6): X48's let-go crossfades end in each, and its landings start
from each (:func:`fade_dip`)."""
HANG_EASE_HOOKS = tuple(TrampolinePatch(
    name=f"{HANG_EASE_SHIM_NAME}_{what}",
    label=f"Player model hang ease: {why} (X22) at VA 0x{va:X}",
    va=va,
    replaced_bytes=_call(va, 0x42E40),
    shim_object=HANG_EASE_SHIM.object_path(HANG_EASE_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_hang_ease",
    float_params=(HANG_STEP, HANG_SPAN),
    bytes_params=(EASE_SHARED,),
) for what, why, va in (
    ("letgo", "the zipline's let-go placement eased", 0x89290),
    ("flap", "the wing flap's placement eased", 0x8944E),
    ("airborne", "the airborne placement eased", 0x8996D)))
"""X22's landings (one each): the CALLs of 0x42E40 that place m_feet at the
centre less 1.0 m in player_jump_init (the let-go), wing_flap and
player_airborne_tick (the cable's end and every airborne tick); the
airborne one lands first, its state block the others'."""
HANG_EASE_GROUND = TrampolinePatch(
    name=f"{HANG_EASE_SHIM_NAME}_ground",
    label="Player model hang ease: a landing's ease goes on on the ground (X22) at VA 0x8672A",
    va=0x8672A,
    replaced_bytes=_call(0x8672A, 0x85920),
    shim_object=HANG_EASE_SHIM.object_path(HANG_EASE_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_hang_ease_ground",
    float_params=(HANG_STEP, HANG_SPAN),
    bytes_params=(EASE_SHARED,),
)
"""X22's fourth landing (Step 2.189b, AZ-711): the walk's CALL of
player_land_classify (0x85920) right after its placement (0x42E40 at
0x866D9, an L2 blind spot): an ease a landing interrupts goes on from where
the last placement drew the body, a step a tick, sharing the airborne
landing's state block."""
G4_HANG_GRAB = 3.69323754
"""garret4's ``m_grab`` height in ``hang`` at t 0 (X9's ``g4_hang_grab``'s z):
how far below the cable the ride hangs his origin, x the model scale."""
HANG_MARGIN = 2.0
"""How much farther than the hang's extra depth (m) X22 still eases a new
drawn offset toward (D115's default): the control's own let-go step is
0.85 m."""


def hang_span(model_scale: float) -> float:
    """X22's span (Step 2.105, AZ-529): the farthest a let-go or an
    airborne placement moves the drawn offset of a body X9 hangs
    ``model_scale`` times garret4's grab under the cable (:func:`hang_scale`,
    Step 2.106), |X - 1| x :data:`G4_HANG_GRAB` + :data:`HANG_MARGIN`
    metres; a farther move (a teleport of the centre alone) keeps the
    game's placement."""
    return abs(model_scale - 1.0) * G4_HANG_GRAB + HANG_MARGIN


HANG_SLOT = 0x43
"""The clip slot the zipline ride plays (``hang``, :data:`BASE_CLIPS`)."""
HANG_GAP = 0.05
"""How far under the cable the top of garret4's ``hang`` pose sits at t 0
(m): his ``m_grab`` 3.693 m over his origin, his top bone 3.643."""


HANG_TOP_HZ = 60.0
"""How finely :func:`hang_top` samples the hang clip's loop, per second of
clip time (the ride plays it at X12's rate, up to 16 times faster)."""


def hang_loop(clip: Clip) -> np.ndarray:
    """The clip times :func:`hang_top` reads over ``clip``'s loop: t 0 to
    its end at :data:`HANG_TOP_HZ`."""
    return np.linspace(0.0, clip.length, max(2, math.ceil(clip.length * HANG_TOP_HZ) + 1))


def hang_top(characters_xbr: bytes, body: Body, fills: dict[int, tuple[str, float]],
             held: Carriers | None = None) -> float:
    """The top of ``body``'s pose on the zipline, model units over its
    origin: the highest its bones reach over the loop of the clip its hang
    slot plays (its own ``hang``, else X11's fill, ``fills``: a baked
    body's ``g4/hang``, an X9 body's stand-in, which the ride plays on
    from hang_start's end; :func:`hang_loop`), else its bind pose's top
    (:attr:`Body.top`).  Not the clip at t 0 alone (Step 2.175b, AZ-599):
    a top that bobs over the loop then rode over the cable by up to
    7.95 m (key_air1 own x2's idle; sitting 2.175b's frames, 265 of 280
    ride ticks over it).  A one-bone rig is drawn by its mesh, not the
    bone (tesla_tree's mesh 8.2 units over it, ruby's bone 1.0 over its
    0.212 top), so its top is the highest vertex of its mesh moved by
    that bone's pose (its bind with no clip; Step 2.118, AZ-536).  A
    carried prop's bones (``held``, the build's
    :attr:`Loadout.carriers`) are left out."""
    clip = fills[HANG_SLOT][0] if HANG_SLOT in fills else next(
        (c for c in body.clips if c.casefold() == BASE_CLIPS[HANG_SLOT]), None)
    keys = {name.casefold(): i for i, name in named_resources(characters_xbr).items()}
    at = keys.get(f"characters/{body.name}/{clip}".casefold()) if clip else None
    motion = read_clip(characters_xbr, parse_toc(characters_xbr)[at].file_offset) if at is not None else None
    rig = Rig.read(characters_xbr, body.name) if motion is not None or len(body.bones) == 1 else None
    if len(body.bones) == 1:
        points = mesh_points(characters_xbr, body.name)
        if points:
            here, turn = ((origins(rig, motion, 0.0)[0], pose(rig, motion, 0.0)[0]) if motion is not None
                          else (rig.positions[0], rig.world[0]))
            turn = qmul(turn, qinv(rig.world[0]))
            bind = rig.positions[0]
            first = max(here[2] + _turn(turn, tuple(v - b for v, b in zip(p, bind)))[2] for p in points)
            if motion is None:
                return first
            return max(first, float(crossfade.highest(rig, crossfade.sample(rig, motion, hang_loop(motion)),
                                                      points).max()))
    if motion is None:
        return body.top
    prop = carriers(rig, held)
    first = max(p[2] for k, p in enumerate(origins(rig, motion, 0.0)) if k not in prop)
    return max(first, float(crossfade.highest(rig, crossfade.sample(rig, motion, hang_loop(motion)),
                                              skip=prop).max()))


def hang_scale(model_scale: float, drawn: float, top: float) -> float:
    """X9's :data:`CLIMB_SCALE` (Step 2.106, AZ-529): the multiple X' of
    garret4's grab (:data:`G4_HANG_GRAB`) below the cable at which a body
    drawn ``drawn`` times its model, its hang pose ``top`` model units
    tall (:func:`hang_top`), hangs that top :data:`HANG_GAP` under the
    cable, as garret4's: town_male_6 own x2 1.724 (its hands at the
    cable, where x2 alone hung its top 1.07 m under it), keylord own x2
    2.308 (the cable no longer across its torso), its loop's highest
    since Step 2.175b (AZ-599).  At x1 too (Step 2.118, AZ-536, D291, D292): a
    shorter body hangs by its top (flicken own's top rode 3.1 m under the
    cable at garret4's grab), and so does a taller one (kingkong own's
    top rode 11 m over it), held over the platforms by X28."""
    return (drawn * top + HANG_GAP) / G4_HANG_GRAB


def hang_eased(body: Body, hung: float) -> bool:
    """Whether X22 eases ``body`` off the zipline: X9 hangs it ``hung``
    times garret4's grab under the cable (:func:`hang_scale`), not his
    own, x1 too (Step 2.118)."""
    return hung != 1.0 and (needs_climb_shim(body) or needs_hang_shim(body, hung))


def install_hang_ease_shim(xbe: bytearray, model_scale: float) -> None:
    """Install X22 (``player_model/hang_ease.c``) at VAs 0x89290, 0x8944E
    and 0x8996D in ``xbe``, one landing each: where the let-go, a wing
    flap or the airborne tick moves the drawn body more than
    :data:`HANG_STEP` against its centre (a body drawn ``model_scale``
    times garret4's grab under the cable letting go of the zipline or
    reaching the cable's end: :func:`hang_scale`), it moves that much a
    placement, so it eases from its hang to its stance, from where it was
    drawn with the aligned node's term (Step 2.175b, AZ-600); the centre,
    and so collision, is the game's (:func:`_install`).  The airborne
    landing goes first: the others share its state block.  A fourth, at
    0x8672A (:data:`HANG_EASE_GROUND`), goes on with an ease a landing
    interrupts, a step a tick on the ground (Step 2.189b, AZ-711).  The
    let-go's crossfade over the floor is X48's (:func:`install_fade_shim`)."""
    params = {HANG_STEP.name: HANG_STEP.default, HANG_SPAN.name: hang_span(model_scale)}
    *rest, airborne = HANG_EASE_HOOKS
    _install(xbe, airborne, HANG_EASE_SHIM, "hang ease", params)
    shared = trampoline_symbol_va(xbe, airborne, EASE_STATE, CHECKOUT, shim_source=HANG_EASE_SHIM.source_path())
    for hook in (*rest, HANG_EASE_GROUND):
        _install(xbe, hook, HANG_EASE_SHIM, "hang ease", params | {EASE_SHARED.name: struct.pack("<I", shared)})


# --- X28: the drawn hang held over every floor under its path (Step 2.118, AZ-529 (b); Step 2.118c) ---
HANG_START_SLOT = 0x44
"""The clip slot hang_start plays (``hang_start``, :data:`BASE_CLIPS`)."""
G4_SPAN = 2.83
"""How far under the cable a hang may reach and need no hold (m): f3's
start platform 3.75 m under it less 0.92 m (garret4's own x1 hang reaches
2.582 m, his hang clip's lowest bone 1.112 m over his origin: Step 2.127);
no floor his collision lets the centre pass over comes closer, so a body
whose drawn hang reaches no deeper (:func:`hold_plan`) needs no hold, and
garret4 drawn at a Model size needs one from x1.098."""
G4_HANG_START = 0.733333349
"""garret4's ``hang_start`` (s): X9 plays a stand-in in it (climb.c)."""
HOLD_CROSSFADE = 7
"""The ticks the margin spreads the change from hang_start's last frame
into the hang clip over (sitting 2.106: keylord own x2's lowest bone
4.124 -> 4.201 .. 4.626 m)."""
HOLD_STAND_INS = (1, 2, 8, 9)
"""The slots whose clip X9 plays for an empty hang_start, in order (idle,
idle_1, walk, run; then the roll's: climb.c's ``stand_in``)."""
HOLD_PRIORS = (*range(1, 10), 13, 14)
"""The slots whose clip the player can be in when it grabs a cable: the
ground state's (idle and its fidgets, walk, run and their backward
ones), for the hang's set-up 0x8A200 has one caller, the ground state's
case at 0x8D149 (after the swim, the use and the landing checks, before
the jump), so a grab starts from the ground [verified static: Step
2.118c's read of the hang's entry].
Each loops, at X12's rate where X11 times it to garret4's (water_tentacle2's
walk its idle at x5.9)."""
HOLD_TICKS = 22
"""hang_start's ticks at 30 Hz (garret4's 0.7333 s): the table's length."""
HOLD_RIDE = 8
"""The ride's first ticks the table looks ahead into (the crossfade from
hang_start into the hang)."""
HOLD_WIDEN = 2
"""How many ticks either way a pose's dip may come early or late with the
grab's state (DESIGN 2.118c 1a): each tick takes the least of these."""
HOLD_PHASE_HZ = 60.0
"""How finely the table samples a prior clip's phase at the grab."""
HOLD_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="hang_hold")
HOLD_SHIM_NAME = "player_model_hang_hold"
"""Its object's name: ``player_model_hang_hold.o`` in the shim build dir."""
HOLD_RAY = FloatParam(
    name="hold_ray", symbol="_player_model_hold_ray", default=0.0,
    label="Player model hang hold ray (X28)",
    description="How far under a point the hold looks for a floor, m: the drawn hang's reach under "
                "the cable (its span and margin) plus 2.")
HOLD_MARGIN = FloatParam(
    name="hold_margin", symbol="_player_model_hold_margin", default=0.0,
    label="Player model hang hold margin (X28)",
    description="How far under its lowest bone the drawn body may reach, m: its mesh under that bone and "
                "a tick of its pose.")
HOLD_AHEAD = FloatParam(
    name="hold_ahead", symbol="_player_model_hold_ahead", default=0.0,
    label="Player model hang hold lookahead (X28)",
    description="How many ticks ahead the ride's hold samples the floors, every one: the drawn hang's "
                "depth and margin past garret4's over the step.")
HOLD_STEP = FloatParam(
    name="hold_step", symbol="_player_model_hold_step", default=0.847,
    label="Player model hang hold step (X28)",
    description="The most, in metres, the hold moves the drawn body a tick: X22's step.")
HOLD_SHARED = BytesParam(
    name="hold_shared", symbol="_player_model_hold_shared", size=4,
    label="Player model hang hold: the ride landing's state block (X28)")
"""The address of the ride landing's state block (:data:`HOLD_STATE`),
which the set-up's and the tick's landings read and write; 0 in the ride's
own landing (its own block)."""
HOLD_TABLE = BytesParam(
    name="hold_table", symbol="_player_model_hold_table", size=4 * HOLD_TICKS,
    label="Player model hang hold: hang_start's table (X28)")
"""hang_start's table (:attr:`HoldPlan.table`), one float a tick: the
least over every prior and phase, for a grab from a prior the build
didn't key."""
HOLD_PRIOR_KEYS = 8
"""How many prior clips X28 keys tables by (their lengths; more fall to
the least table)."""
HOLD_PHASES = 12
"""Each keyed prior's tables, by its phase at the grab in twelfths."""
HOLD_PRIOR_TABLES = BytesParam(
    name="hold_priors", symbol="_player_model_hold_priors",
    size=4 * (HOLD_PRIOR_KEYS + HOLD_PRIOR_KEYS * HOLD_PHASES * HOLD_TICKS),
    label="Player model hang hold: hang_start's table per prior and phase (X28)")
"""The prior clips' lengths (:data:`HOLD_PRIOR_KEYS` floats, 0 unused),
then per prior and phase twelfth a table as :data:`HOLD_TABLE`
(:attr:`HoldPlan.priors`; Step 2.175b, AZ-574)."""
HOLD_FLOOR = 3.75
"""How far under the cable f3's start platform lies (m), where a grab
stands: X28's gate weighs hang_start's dips against it (Step 2.175b,
AZ-574)."""
HOLD_DIP = 0.05
"""How far through the floor it grabs from (m) a drawn hang_start may dip
and need no hold: X28's gate (Step 2.175b, AZ-574)."""
HOLD_LOOP_TIMES = 64
"""How many times over its loop X28's ride table samples the hang clip
(Step 2.189b, AZ-713)."""
HOLD_LOOP = BytesParam(
    name="hold_loop", symbol="_player_model_hold_loop", size=4 * (1 + HOLD_LOOP_TIMES),
    label="Player model hang hold: the hang clip's lowest point over its loop (X28)")
"""The hang clip's float32 length (0: none), then its lowest drawn point
over the origin (m) at :data:`HOLD_LOOP_TIMES` times evenly over its loop
(:attr:`HoldPlan.loop`), which the ride takes at its layer's own time
(Step 2.189b, AZ-713)."""
HOLD_CROSS = BytesParam(
    name="hold_cross", symbol="_player_model_hold_cross", size=4 * (3 + HOLD_RIDE + HOLD_TICKS),
    label="Player model hang hold: the ride's crossfade into the hang clip (X28)")
"""hang_start's clip's float32 length (0: none), its time at the ride's
first tick and its rate, then the lowest drawn point over the origin (m)
at each of the :data:`HOLD_RIDE` ticks the ride's anim change crosses
from it into the hang clip (:attr:`HoldPlan.cross`), which the ride takes
by the hang layer's weight, then per hang_start tick those dips ahead of
it as its table takes a dip (:func:`hold_ahead`), which hang_start adds
where the ride will restart its clip on a layer of its own (Step 2.199,
AZ-713)."""
HOLD_STATE = "_player_model_hold_state"
"""The state block's symbol in the ride's landing."""
HOLD_HOOKS = tuple(TrampolinePatch(
    name=f"{HOLD_SHIM_NAME}_{what}",
    label=f"Player model zipline: {why} (X28) at VA 0x{va:X}",
    va=va,
    replaced_bytes=replaced,
    shim_object=HOLD_SHIM.object_path(HOLD_SHIM_NAME, CHECKOUT),
    shim_symbol=f"_c_player_model_hang_hold_{what}",
    float_params=(HOLD_RAY, HOLD_MARGIN, HOLD_AHEAD, HOLD_STEP),
    bytes_params=(HOLD_SHARED, HOLD_TABLE, HOLD_PRIOR_TABLES, HOLD_LOOP, HOLD_CROSS),
) for what, why, va, replaced in (
    ("ride", "the ride drawn over the floors under its path", 0x8AB3F, _call(0x8AB3F, 0x8C080)),
    ("setup", "hang_start's set-up drawn over the floor", 0x8A4F0, _call(0x8A4F0, 0x8C080)),
    ("tick", "hang_start's glide drawn over the floor", 0x8D091, bytes.fromhex("8b6d3085ed"))))
"""X28's landings, one object each, the ride's first (its state block
the others share): the ride's (0x8A510) CALL of the state's landing
0x8C080 after X9's 0x42E40; hang_start's set-up's (0x8A480) CALL of it
after 0x42430; and the dispatcher's state-0x105 case (mov ebp,[ebp+0x30];
test ebp,ebp), hang_start's every later tick."""


@dataclass(frozen=True)
class HoldPlan:
    """X28's numbers for a build (:func:`hold_plan`), metres and ticks."""

    span: float      # how far under the cable the drawn hang reaches at its deepest
    ray: float       # HOLD_RAY
    margin: float    # HOLD_MARGIN
    ahead: int       # HOLD_AHEAD
    table: tuple[float, ...] = ()   # HOLD_TABLE (only when needed)
    priors: tuple[tuple[float, tuple[tuple[float, ...], ...]], ...] = ()   # HOLD_PRIOR_TABLES: (length, tables)
    dip: float = 0.0   # how far through the floor it grabs from some grab's hang_start dips the drawn body
    loop: tuple[float, ...] = ()   # HOLD_LOOP: the hang clip's length, then its lowest point over its loop
    cross: tuple[float, ...] = ()  # HOLD_CROSS: hang_start's clip, the ride's crossfade into the hang clip, its dips ahead
    fade_ray: float = 0.0    # FADE_RAY (X48): 0 where no let-go's or landing's crossfade dips HOLD_DIP past the ground
    # clips' lowest or, where X28 is needed, past it and HOLD_DIP under the origin (Step 2.207d)
    fade_sole: float = 0.0   # FADE_SOLE: the drawn mesh under the lowest bone, m
    fade_low: float = 0.0    # FADE_LOW: the ground clips' own lowest drawn point under the origin, 0 or less
    fade_loose: bytes = b""  # FADE_LOOSE: the bones X48 leaves out of the lowest, a bit each (:func:`loose_bones`)

    @property
    def needed(self) -> bool:
        """Whether the hang reaches deeper than garret4's (:data:`G4_SPAN`),
        or some grab's hang_start dips the drawn body more than
        :data:`HOLD_DIP` through the floor it grabs from (Step 2.175b,
        AZ-574)."""
        return self.span > G4_SPAN or self.dip > HOLD_DIP


def hold_plan(characters: bytes, body: Body, fills: dict[int, tuple[str, float]], drawn: float,
              hung: float, roll: str | None = None, held: Carriers | None = None) -> HoldPlan:
    """X28's plan for ``body`` drawn ``drawn`` times its model and hung
    ``hung`` (:func:`hang_scale`) times garret4's grab under the cable,
    its slots X11's ``fills`` (and its own clips), its roll's clip
    ``roll`` (X9's last stand-in): the span is that depth less its lowest
    bone (x ``drawn``) at its lowest over the hang clip and at the last
    frame of hang_start's clip; the margin ``drawn`` x (its bind mesh
    under its lowest bind bone, the sole, plus the most its lowest bone
    moves a tick over hang_start's clip in 22 ticks, the hang clip at 30
    ticks a second and the crossfade between them: the live hold reads
    the last drawn pose); the lookahead every tick the span and the
    margin past :data:`G4_SPAN` take at the step (Step 2.118c's review:
    the rise is owed to the margin over the floor, not garret4's depth);
    the ray the span plus the margin plus 2 m, so from the centre (under
    the cable) it passes the lowest drawn point on every body.
    hang_start's tables (:func:`hold_tables`): the least over every
    prior and phase, and per prior clip (by its length) and phase
    twelfth, which X28 picks at the set-up by the grab's own prior; and
    the dip, the most hang_start's drawn body passes under the floor it
    grabs from (:data:`HOLD_FLOOR` under the cable, the glide's origin
    going from there to the hang's depth over its 22 ticks): X28 is
    needed where the hang is deeper than garret4's or the dip passes
    :data:`HOLD_DIP` past where the body's own ground clips (the priors
    at every phase) draw it (Step 2.175b, AZ-574: the gate counted the
    hang alone, so overlord own x2's glide, 0.49 m through f3's start
    platform, was never held; firedrake own x2's grab from its fly dips
    4.29 m, as its fly does on the ground: no hold).  X48's numbers
    where :func:`fade_dip`'s crossfades take the drawn body more than
    :data:`HOLD_DIP` past the ground clips' own lowest, or, where X28 is
    needed, past that lowest and more than :data:`HOLD_DIP` under the
    origin: its ride's exits leave the held ride at X22's eased origin,
    not at the stance (Step 2.207d's sitting: booblord, 8 cm under her
    origin and 1.9 cm past her ground clips' lowest, went 0.73 m through
    f3's end platform off the cable's end with no X48, main's held her at
    its line).  A body whose crossfades never pass that lowest, the line
    X48 holds, by 1 mm gets none, as on main (garret4 x2: 0.41 m under his
    origin, over his line 0.43 m under it; armed, X48 lifted him 0 on
    every tick of his cable's end and let-go; guard_water's crossfade at
    a ground clip's own pose meets its line up to rounding).  A carried prop's
    bones (``held``, the build's :attr:`Loadout.carriers`) are left out."""
    rig = Rig.read(characters, body.name)
    toc, names = parse_toc(characters), {k.casefold(): i for i, k in named_resources(characters).items()}

    def motion(name: str | None) -> Clip | None:
        at = names.get(f"characters/{body.name}/{name}".casefold()) if name else None
        return read_clip(characters, toc[at].file_offset) if at is not None else None

    def slot(k: int) -> tuple[Clip, float] | None:
        """The clip ``body`` plays in slot ``k`` (X11's fill, else its own) and its rate (X12's for
        a garret4-timed fill: its length over his)."""
        name, length = fills[k] if k in fills else (
            next((c for c in body.clips if c.casefold() == BASE_CLIPS[k]), None), 0.0)
        clip = motion(name)
        return None if clip is None else (clip, clip.length / length if length > 0 else 1.0)

    bind_low = min((p[2] for p in rig.positions), default=0.0)
    hang = slot(HANG_SLOT)
    start = slot(HANG_START_SLOT)
    if start is not None:
        start = (start[0], 1.0)   # 0x42430 plays it at rate 1 (no X12 there)
    else:   # X9's stand-in in garret4's time: a shorter one stretched over it (climb.c's slower)
        stand = next((s[0] for s in map(slot, HOLD_STAND_INS) if s is not None), None) or motion(roll)
        start = None if stand is None else (stand, min(1.0, stand.length / G4_HANG_START))

    prop = carriers(rig, held)

    def lows(clip: Clip | None, n: int, length: float) -> list[float]:
        if clip is None or not rig.bones:
            return [bind_low]
        return [min(p[2] for j, p in enumerate(origins(rig, clip, length * k / n)) if j not in prop)
                for k in range(n + 1)]

    on_hang = lows(hang[0], max(1, round(30 * hang[0].length)), hang[0].length) if hang else [bind_low]
    on_start = lows(start[0], 22, start[0].length) if start else [bind_low]
    steps = [abs(b - a) for seq in (on_hang, on_start) for a, b in zip(seq, seq[1:])] or [0.0]
    hang_step = max((abs(b - a) for a, b in zip(on_hang, on_hang[1:])), default=0.0)
    pose_step = max(max(steps), abs(on_hang[0] - on_start[-1]) / HOLD_CROSSFADE + hang_step)
    bounds = mesh_bounds(characters, body.name)
    sole = max(0.0, bind_low - bounds[0][2]) if bounds else 0.0
    span = hung * G4_HANG_GRAB - drawn * min(min(on_hang), on_start[-1])
    margin = abs(drawn) * (sole + pose_step)
    priors = []
    for k in HOLD_PRIORS:
        s = slot(k)
        if s is not None and s not in priors:
            priors.append(s)
    points = mesh_points(characters, body.name) if len(rig.bones) == 1 else None
    table, keyed = hold_tables(rig, start, hang, priors, drawn, sole, points, held=held)
    depth = hung * G4_HANG_GRAB
    rest = min((float(((crossfade.lowest(rig, crossfade.sample(rig, clip, np.arange(
        0.0, max(clip.length, 1e-3), 1.0 / HOLD_PHASE_HZ)), points, prop) - (0.0 if points is not None else sole))
                        * drawn).min()) for clip, _ in priors), default=0.0)   # the ground clips' own lowest
    dip = max((j / HOLD_TICKS * (depth - HOLD_FLOOR) - v for j, v in enumerate(table)), default=0.0) - max(0.0, -rest)
    into = [s for s in map(slot, EASE_INTO) if s is not None]
    deep = fade_dip(rig, hang, into, [s for s in map(slot, FADE_GROUND) if s is not None], drawn, sole, points,
                    held=held)
    low = min(0.0, rest)   # held where a crossfade dips past the ground clips' own lowest, as the gate's dip
    plan = HoldPlan(span, span + margin + 2.0, margin, 0, dip=dip)
    # where X28 holds the ride, its exits leave the held ride at X22's eased origin, not the stance, so HOLD_DIP is
    # no allowance past the ground clips' lowest there: a crossfade dip 1 mm past that lowest (X48's line; at a ground
    # clip's own pose it meets the line up to rounding, guard_water's -4.4e-16 m) and HOLD_DIP under the origin arms
    # X48; one that never passes the line gets none, as on main (garret4 x2's, armed, lifted 0: Step 2.207d)
    if deep < low - HOLD_DIP or (plan.needed and deep < min(low - 1e-3, -HOLD_DIP)):
        plan = replace(plan, fade_ray=3.0 - deep, fade_sole=drawn * sole, fade_low=low,
                       fade_loose=loose_mask(loose_bones(rig, held)))
    if not plan.needed:
        return plan
    ahead = math.ceil((span + margin - G4_SPAN) / HOLD_STEP.default) if span > G4_SPAN else 0
    loop = ()
    if hang is not None and hang[0].length > 0:   # the ride's pose at its own time (Step 2.189b, AZ-713)
        at = np.arange(HOLD_LOOP_TIMES) * (hang[0].length / HOLD_LOOP_TIMES)
        lows = (crossfade.lowest(rig, crossfade.sample(rig, hang[0], at), points, prop)
                - (0.0 if points is not None else sole)) * drawn
        loop = (struct.unpack("<f", struct.pack("<f", hang[0].length))[0], *map(float, lows))
    cross = ()
    if start is not None and hang is not None and start[0].length > 0 and hang[0].length > 0:
        # the ride's anim change crossing from hang_start's clip into the hang clip (Step 2.199, AZ-713)
        old, new = ride_cross(rig, start, hang)
        lows = (crossfade.lowest(rig, crossfade.blend(old, new, np.array([crossfade.fade_weight(k)
                                                                           for k in range(HOLD_RIDE)])[:, None]),
                                 points, prop) - (0.0 if points is not None else sole)) * drawn
        cross = (*struct.unpack("<3f", struct.pack("<3f", start[0].length,
                                                    min(HOLD_TICKS / 30.0 * start[1], start[0].length), start[1])),
                 *map(float, lows), *hold_ahead([math.inf] * HOLD_TICKS + [float(v) for v in lows]))
    return replace(plan, ahead=ahead, table=table, priors=keyed, loop=loop, cross=cross)


def ride_cross(rig: Rig, start: tuple[Clip, float], hang: tuple[Clip, float]) -> tuple[crossfade.Pose, crossfade.Pose]:
    """The two layers of the ride's first :data:`HOLD_RIDE` ticks when its
    anim change starts the hang clip on a layer of its own: hang_start's
    clip ``start`` going on from its 22nd tick at its rate (held at its
    end) and the hang clip ``hang`` from t 0 at its rate, looping; sitting
    2.189b's key_air1 own x2 frames fit it to 1 mm (whose ride replayed
    its idle on another layer than hang_start's), while guard_air's and
    water_tentacle1's own x2 replayed it on the same layer, as 0xCAD40
    does for a clip a playing layer holds when no free layer holding it
    comes first (Step 2.199, AZ-713)."""
    (clip, rate), (hang_clip, hang_rate) = start, hang
    old = crossfade.sample(rig, clip, [min((HOLD_TICKS + k) / 30.0 * rate, clip.length) for k in range(HOLD_RIDE)])
    new = crossfade.sample(rig, hang_clip, [(k / 30.0 * hang_rate) % hang_clip.length for k in range(HOLD_RIDE)])
    return old, new


def hold_table(rig: Rig, start: tuple[Clip, float] | None, hang: tuple[Clip, float] | None,
               priors: list[tuple[Clip, float]], drawn: float, sole: float,
               points=None, step: float = HOLD_STEP.default, ticks: int = HOLD_TICKS,
               held: Carriers | None = None) -> tuple[float, ...]:
    """hang_start's least table (:func:`hold_tables`)."""
    return hold_tables(rig, start, hang, priors, drawn, sole, points, step, ticks, held)[0]


def hold_tables(rig: Rig, start: tuple[Clip, float] | None, hang: tuple[Clip, float] | None,
                priors: list[tuple[Clip, float]], drawn: float, sole: float,
                points=None, step: float = HOLD_STEP.default, ticks: int = HOLD_TICKS,
                held: Carriers | None = None) -> tuple[tuple[float, ...],
                                                       tuple[tuple[float, tuple[tuple[float, ...], ...]], ...]]:
    """hang_start's tables for X28 (Step 2.118c, AZ-529 (b), D293): per
    tick t of its 22 (0 the set-up's, drawn first) the least over every
    tick j from t to the ride's eighth of low(j) + ``step`` x (j - t), so
    a hold that rises a step a tick clears every dip ahead: low(j), m
    over the drawn origin, is the least of low'(j - 2 .. j + 2)
    (:data:`HOLD_WIDEN`), low'(j) the lowest drawn point (the lowest bone
    less the ``sole``, x ``drawn``; a one-bone rig's mesh ``points``
    through its bone, :func:`crossfade.lowest`) of the pose drawn at
    tick j: for j under 8 the crossfade (:func:`crossfade.fade_weight`
    j ticks in) from every phase of every ``priors`` clip (at its rate,
    looping, its time advancing as it fades) into ``start``'s clip at
    j / 30 x its rate (X9's stretch), the least over them; to j 21 that
    clip; then (the ride) the crossfade from it into the ``hang`` clip
    (j - 22 ticks in), or, where the hang is the same clip (an X9
    stand-in X11 also gave the hang slot), that clip going on from
    hang_start's end at the hang's rate, no crossfade: 0xCAD40 plays a
    clip again on the layer that holds it (where a layer before it holds
    the clip, the ride restarts it there, a crossfade, whose dips X28
    adds at run time from :attr:`HoldPlan.cross`: Step 2.199, AZ-713).
    Sitting 2.118's ride frames fit both to 1 mm (guard_air, kingkong,
    guard_earth, keylord and town_male_6 own x2), its hang_start frames
    the crossfade (:mod:`azurik_mod.patches._player_crossfade`).
    ``ticks`` entries (more than 22 reads the ride's too, as the build's
    offline gate does).  A carried
    prop's bones (``held``) are left out.  Returns that least table and,
    per prior clip (by its float32 length, the first
    :data:`HOLD_PRIOR_KEYS`; priors of one length merged) and phase
    twelfth (:data:`HOLD_PHASES`), the table of the crossfade from those
    phases alone (Step 2.175b, AZ-574: the set-up picks one by the grab's
    own prior, sitting 2.175b's frames matching the crossfade from
    firedrake own x2's idle at t 0.567 to 1 mm).  A twelfth no sampled
    phase falls in takes its nearest phase."""
    if start is None:
        return (), ()
    clip, rate = start
    n = HOLD_TICKS + HOLD_RIDE
    on = crossfade.sample(rig, clip, [min(j / 30.0 * rate, clip.length) for j in range(n)])
    under = 0.0 if points is not None else sole

    fades, starts = [], []
    for prior, p_rate in priors:
        phases = np.arange(0.0, prior.length, 1.0 / HOLD_PHASE_HZ) if prior.length > 0 else np.zeros(1)
        starts.append(phases)
        fades.append([(phases + j * p_rate / 30.0) % prior.length if prior.length > 0 else phases
                      for j in range(int(crossfade.FADE_TICKS) + 1)])
    # each clip sampled once at all its times, and every tick's pose lowered in one pass (Step X.81c)
    fading = [j for j in range(n) if j < crossfade.FADE_TICKS] if priors else []
    olds = [crossfade.sample(rig, prior, np.concatenate([times[j] for j in fading]))
            for (prior, _), times in zip(priors, fades)]
    rides = range(HOLD_TICKS, n)
    again = ride = None
    if hang is not None and hang[0] == clip:   # 0xCAD40 plays it again on its layer
        again = crossfade.sample(rig, clip, [(HOLD_TICKS / 30.0 * rate + (j - HOLD_TICKS) / 30.0 * hang[1]) % clip.length
                                             if clip.length > 0 else 0.0 for j in rides])
    elif hang is not None:
        ride = crossfade.sample(rig, hang[0], [min((j - HOLD_TICKS) / 30.0 * hang[1], hang[0].length) for j in rides])
    poses = []
    for j in range(n):
        new = crossfade.part(on, j, j + 1)
        if j < crossfade.FADE_TICKS and priors:
            for old, times in zip(olds, fades):
                size = len(times[j])
                poses.append(crossfade.blend(crossfade.part(old, j * size, (j + 1) * size), new,
                                             crossfade.fade_weight(j)))
        elif j >= HOLD_TICKS and again is not None:
            poses.append(crossfade.part(again, j - HOLD_TICKS, j - HOLD_TICKS + 1))
        elif j >= HOLD_TICKS and ride is not None:
            poses.append(crossfade.blend(new, crossfade.part(ride, j - HOLD_TICKS, j - HOLD_TICKS + 1),
                                         crossfade.fade_weight(j - HOLD_TICKS)))
        else:
            poses.append(new)
    lowered = iter([(low - under) * drawn for low in crossfade.lowest_many(rig, poses, points, carriers(rig, held))])
    lows, per_phase = [], [[] for _ in priors]   # per prior: each crossfade tick's lows over its phases
    for j in range(n):
        if j < crossfade.FADE_TICKS and priors:
            got = []
            for k in range(len(priors)):
                arr = next(lowered)
                per_phase[k].append(arr)
                got.append(arr.min())
            lows.append(min(got))
        else:
            lows.append(float(next(lowered)[0]))
    def table_of(lows: list[float]) -> tuple[float, ...]:
        return hold_ahead(lows, step, ticks)

    keyed: dict[float, list[tuple[float, ...]]] = {}
    for (prior, _), phases, arrs in zip(priors, starts, per_phase):
        key = struct.unpack("<f", struct.pack("<f", prior.length))[0]
        if not arrs or (key not in keyed and len(keyed) == HOLD_PRIOR_KEYS):
            continue
        frac = phases / prior.length if prior.length > 0 else np.zeros(len(phases))
        fade = len(arrs)
        tables = []
        for b in range(HOLD_PHASES):
            sel = (frac >= b / HOLD_PHASES) & (frac < (b + 1) / HOLD_PHASES)
            if not sel.any():
                sel = np.abs(frac - (b + 0.5) / HOLD_PHASES) == np.abs(frac - (b + 0.5) / HOLD_PHASES).min()
            tables.append(table_of([float(arrs[j][sel].min()) for j in range(fade)] + lows[fade:]))
        keyed[key] = tables if key not in keyed else [tuple(map(min, a, b)) for a, b in zip(keyed[key], tables)]
    return table_of(lows), tuple((key, tuple(tables)) for key, tables in keyed.items())


def hold_ahead(lows: list[float], step: float = HOLD_STEP.default, ticks: int = HOLD_TICKS) -> tuple[float, ...]:
    """Per tick t of the first ``ticks`` the least over every tick j from t
    on of ``lows``' least within :data:`HOLD_WIDEN` of j plus ``step`` x
    (j - t): where a hold that rises a step a tick stands at t to clear
    every dip ahead (:func:`hold_tables`, :attr:`HoldPlan.cross`)."""
    n = len(lows)
    wide = [min(lows[max(0, j - HOLD_WIDEN):j + HOLD_WIDEN + 1]) for j in range(n)]
    return tuple(min(wide[j] + step * (j - t) for j in range(t, n)) for t in range(ticks))


def loose_bones(rig: Rig, held: Carriers | None = None) -> frozenset[int]:
    """The bones of ``rig`` that bear no weight, which X48 leaves out of
    the lowest (Step 2.192, AZ-746): a carried prop's (:func:`carriers`)
    and every bone of a hair or cloth chain (a name
    :data:`~azurik_mod.assets.model_chains.KINDS` finds, and every bone
    under it): booblord's sash flap swung 0.36 m through the floor in the
    touchdown she borrows (AZ-728) and X48 floated her whole body 0.24 m
    over it."""
    out = set(carriers(rig, held))
    for k, b in enumerate(rig.bones):
        if any(rx.search(b.name) for rx in CHAIN_KINDS.values()) or (b.parent >= 0 and b.parent in out):
            out.add(k)
    return frozenset(out)


def loose_mask(bones: frozenset[int]) -> bytes:
    """``bones`` as X48's :data:`FADE_LOOSE` mask (bit ``b & 7`` of byte
    ``b >> 3``); a bone past its 256 raises :class:`ValueError` (D35)."""
    out = bytearray(FADE_LOOSE.size)
    for b in bones:
        if b >= 8 * len(out):
            raise ValueError(f"X48: bone {b} is past the crossfade floor's {8 * len(out)}-bone mask")
        out[b >> 3] |= 1 << (b & 7)
    return bytes(out)


def fade_dip(rig: Rig, hang: tuple[Clip, float] | None, into: list[tuple[Clip, float]],
             ground: list[tuple[Clip, float]], drawn: float, sole: float, points=None,
             held: Carriers | None = None) -> float:
    """X48's gate (Step 2.189b, AZ-706, AZ-711): the lowest drawn point
    under the origin (m; the lowest bone less the ``sole``, x ``drawn``; a
    one-bone rig's mesh ``points``) that the crossfades X48 holds reach in
    their :data:`FADE_TICKS` ticks: off the zipline, every phase of the
    ``hang`` clip (at its rate, going on as it fades) crossing
    (:func:`crossfade.fade_weight`) into each ``into`` clip (the airborne
    slots, :data:`EASE_INTO`) from its t 0 at its rate (guard_air own
    x2's 3.29 m under its origin 4 ticks after its let-go, sitting
    2.118c); and at a landing, every phase of each ``into`` clip crossing
    into each ``ground`` clip (:data:`FADE_GROUND`) from its t 0
    (guard_air own x2's 2.95 m through the end platform 2 ticks after
    landing off the cable's end, sitting 2.127); and at a takeoff, every
    phase of each ``ground`` clip crossing into each ``into`` clip from
    its t 0 (guard_air own x2's 2.84 m through the floor 3 ticks into
    f6's standing jump, 3.82 m 3 ticks after running off a ledge: Step
    2.189b's record sitting; Step 2.199, AZ-706).  0 with none.  The
    lowest is the weight-bearing bones' (:func:`loose_bones` left out,
    as X48 reads it: Step 2.192, AZ-746)."""
    under = 0.0 if points is not None else sole
    skip = loose_bones(rig, held)

    def least(old: tuple[Clip, float], news: list[tuple[Clip, float]]) -> float:
        clip, rate = old
        phases = np.arange(0.0, clip.length, 1.0 / HOLD_PHASE_HZ) if clip.length > 0 else np.zeros(1)
        # each clip sampled once at all its times, and every tick's pose lowered in one pass (Step X.81c)
        was = crossfade.sample(rig, clip, np.concatenate([(phases + j * rate / 30.0) % clip.length if clip.length > 0
                                                          else phases for j in range(FADE_TICKS)
                                                          if j < crossfade.FADE_TICKS]))
        ons = [crossfade.sample(rig, new_clip, [min(j / 30.0 * new_rate, new_clip.length) for j in range(FADE_TICKS)])
               for new_clip, new_rate in news]
        poses = []
        for j in range(FADE_TICKS):
            for on in ons:
                new = crossfade.part(on, j, j + 1)
                poses.append(crossfade.blend(crossfade.part(was, j * len(phases), (j + 1) * len(phases)), new,
                                             crossfade.fade_weight(j)) if j < crossfade.FADE_TICKS else new)
        got = 0.0
        for low in crossfade.lowest_many(rig, poses, points, skip):
            got = min(got, float(((low - under) * drawn).min()))
        return got

    pairs = (([(hang, into)] if hang is not None and into else []) + [(old, ground) for old in into if ground]
             + [(old, into) for old in ground if into])
    return min((least(old, news) for old, news in pairs), default=0.0)


def install_hold_shim(xbe: bytearray, plan: HoldPlan) -> None:
    """Install X28 (``player_model/hang_hold.c``) at VAs 0x8AB3F (the
    ride), 0x8A4F0 (hang_start's set-up) and 0x8D091 (its later ticks)
    in ``xbe`` (either release), one landing each, the set-up's and the
    tick's with the ride landing's state block: the drawn hang no lower
    than any floor under the centre less its lowest bone, eased off it a
    step a tick and risen early for the floors ``plan.ahead`` ticks ahead
    and hang_start's dips (``plan.table``, and ``plan.priors``' table the
    grab's prior picks: Step 2.175b, AZ-574), at most a step a tick, the
    ride's pose read at its hang clip's own time from ``plan.loop`` and its
    steps on the drawn lowest point (Step 2.189b, AZ-713), the ride's
    crossfade into the hang clip from ``plan.cross`` and hang_start past its
    prior's crossfade by its table alone, and by that crossfade's dips too
    where the ride will play one (Step 2.199, AZ-713)
    (:func:`hold_plan`, :func:`_install`)."""
    keys = [key for key, _ in plan.priors] + [0.0] * (HOLD_PRIOR_KEYS - len(plan.priors))
    tables = [v for _, per in plan.priors for table in per for v in table]
    params = {HOLD_RAY.name: plan.ray, HOLD_MARGIN.name: plan.margin, HOLD_AHEAD.name: float(plan.ahead),
              HOLD_STEP.name: HOLD_STEP.default, HOLD_TABLE.name: struct.pack(f"<{len(plan.table)}f", *plan.table),
              HOLD_PRIOR_TABLES.name: struct.pack(f"<{len(keys) + len(tables)}f", *keys, *tables),
              HOLD_LOOP.name: struct.pack(f"<{1 + HOLD_LOOP_TIMES}f", *(plan.loop or (0.0,) * (1 + HOLD_LOOP_TIMES))),
              HOLD_CROSS.name: struct.pack(f"<{3 + HOLD_RIDE + HOLD_TICKS}f",
                                           *(plan.cross or (0.0,) * (3 + HOLD_RIDE + HOLD_TICKS)))}
    ride, *rest = HOLD_HOOKS
    _install(xbe, ride, HOLD_SHIM, "hang hold", params)
    shared = trampoline_symbol_va(xbe, ride, HOLD_STATE, CHECKOUT, shim_source=HOLD_SHIM.source_path())
    for hook in rest:
        _install(xbe, hook, HOLD_SHIM, "hang hold", params | {HOLD_SHARED.name: struct.pack("<I", shared)})


# --- X48: a big body's crossfade off the zipline and into a landing drawn over the floor (Step 2.189b) ---
FADE_TICKS = 12
"""The ticks X48 holds after the player leaves the ride, lands or takes off (the anim
layers' 7.5-tick crossfade and 2 more either way)."""
FADE_GROUND = (1, 8, 9)
"""The slots the ground state plays at a soft landing (idle, walk, run:
its anim change at 0x864DA, before the placement at 0x866D9): X48's
landings cross into each, and its takeoffs from each (:func:`fade_dip`)."""
FADE_HOOK_VA = 0x42237
"""critter_model_matrix's (0x42200) CALL of glide_origin (0x42070), the
drawn origin before the aligned-node term, which X48 replaces."""
FADE_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="fade_floor")
FADE_SHIM_NAME = "player_model_fade_floor"
"""Its object's name: ``player_model_fade_floor.o`` in the shim build dir."""
FADE_RAY = FloatParam(
    name="fade_ray", symbol="_player_model_fade_ray", default=0.0,
    label="Player model crossfade floor: its ray (X48)",
    description="How far under the centre the crossfade's hold looks for a floor, m (0: no hold): 3 m past the "
                "crossfades' lowest point under the drawn origin.")
FADE_SOLE = FloatParam(
    name="fade_sole", symbol="_player_model_fade_sole", default=0.0,
    label="Player model crossfade floor: the mesh under the lowest bone (X48)",
    description="How far the drawn mesh reaches under the lowest posed bone, m.")
FADE_LOW = FloatParam(
    name="fade_low", symbol="_player_model_fade_low", default=0.0,
    label="Player model crossfade floor: the ground clips' own lowest (X48)",
    description="How far under the floor the body's own ground clips draw it at its stance, m (0 or less): the "
                "hold keeps the drawn lowest point no lower.")
FADE_CAMERA_VA = 0x41FB0
"""The camera point's (0x41F40) CALL of critter_model_matrix (0x42200),
which puts X8's point into the world through the drawn origin: X48 lifts
no origin for it (Step 2.192, AZ-746)."""
FADE_CAMERA = BytesParam(
    name="fade_camera", symbol="_player_model_fade_camera", size=4,
    label="Player model crossfade floor: the camera point's return from 0x42200 (X48)")
"""Its CALL's end in the build's own release (:func:`install_fade_shim`)."""
FADE_LOOSE = BytesParam(
    name="fade_loose", symbol="_player_model_fade_loose", size=32,
    label="Player model crossfade floor: the bones left out of the lowest (X48)")
"""A bit a bone (:func:`loose_bones`, :func:`loose_mask`)."""
FADE_HOOK = TrampolinePatch(
    name=FADE_SHIM_NAME,
    label=f"Player model crossfade floor: off the zipline, at a landing and a takeoff (X48) at VA 0x{FADE_HOOK_VA:X}",
    va=FADE_HOOK_VA,
    replaced_bytes=_call(FADE_HOOK_VA, 0x42070),
    shim_object=FADE_SHIM.object_path(FADE_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_fade_floor",
    float_params=(FADE_RAY, FADE_SOLE, FADE_LOW),
    bytes_params=(FADE_CAMERA, FADE_LOOSE),
)


def install_fade_shim(xbe: bytearray, plan: HoldPlan) -> None:
    """Install X48 (``player_model/fade_floor.c``) at VA 0x42237 in
    ``xbe`` (either release) where ``plan``'s crossfades dip
    (:attr:`HoldPlan.fade_ray`, :func:`fade_dip`): for the player's species
    within :data:`FADE_TICKS` of leaving the zipline, landing or taking off
    (Step 2.199, AZ-706), the drawn
    origin is raised so each weight-bearing bone's drawn lowest point (the
    origin, 0x402E0's term and the drawn scale x the bone, less the mesh
    under the lowest) is no lower than the lower of the floors under that
    bone itself (Step 2.200c, AZ-780: its x, y in the world, cast from the
    ray over the centre's height) and under the centre plus
    :attr:`HoldPlan.fade_low`; the pose is the frame's, so it lifts only
    as far as the pose dips, the lift moving at most :data:`HOLD_STEP`'s
    0.847 m a tick and past the window letting go a step a tick (Step
    2.189b, AZ-706, AZ-711; D293's step; :func:`_install`), but for a
    landing's (onto the ground or, since Step 2.200b, a slope), which holds
    the lowest point at the floor exactly over its window (Step 2.200,
    AZ-706, D800: "Stop at the floor"; a slide's end at a slope's foot too
    since Step 2.200c, AZ-780) unless it ends a fall begun off the
    ride under 24 ticks before (Step 2.200b, AZ-780, D815: a step a tick, as
    the let-go; a lift that met its need kept the tick its need first falls
    more than a step under it, Step 2.200c).  The lowest
    bone is a weight-bearing one (``plan.fade_loose`` left out), and the
    camera point's matrix (:data:`FADE_CAMERA_VA`) keeps the game's
    origin (Step 2.192, AZ-746)."""
    camera, _, _ = xbe_site(xbe, FADE_CAMERA_VA, _call(FADE_CAMERA_VA, 0x42200))
    _install(xbe, FADE_HOOK, FADE_SHIM, "crossfade floor",
             {FADE_RAY.name: plan.fade_ray, FADE_SOLE.name: plan.fade_sole, FADE_LOW.name: plan.fade_low,
              FADE_CAMERA.name: struct.pack("<I", camera + 5), FADE_LOOSE.name: plan.fade_loose})


# --- X23: a baked body drawn at a model scale goes over a ladder's top (Step 2.106) ---
OVER_TOP_HOOK_VA = 0x87F65
"""The top dismount's (0x87950) CALL of the state's landing 0x8C080 right
after its climb_up_edge setter (0x87F47) and rate (0x87F55), which X23
replaces."""
OVER_TOP_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="over_top")
OVER_TOP_SHIM_NAME = "player_model_over_top"
"""Its object's name: ``player_model_over_top.o`` in the shim build dir."""
OVER_FEET_K = FloatParam(
    name="over_feet_k", symbol="_player_model_over_feet_k", default=1.0,
    label="Player model ladder and hoist: the end term (X23)",
    description="1: the glide's end moves (D - 1) x garret4's m_feet; 0 on a body with no clips, whose root "
                "rides his m_feet / D (the start term kept).")
OVER_TOP_HOOK = TrampolinePatch(
    name=OVER_TOP_SHIM_NAME,
    label=f"Player model ladder: over the top onto the floor at a model scale (X23) at VA 0x{OVER_TOP_HOOK_VA:X}",
    va=OVER_TOP_HOOK_VA,
    replaced_bytes=_call(OVER_TOP_HOOK_VA, 0x8C080),
    shim_object=OVER_TOP_SHIM.object_path(OVER_TOP_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_over_top",
    float_params=(OVER_FEET_K,),
)
OVER_HOIST_HOOK_VA = 0x86DAE
"""The hoist's (0x86920) CALL of the state's landing 0x8C080 right after
its setter (0x86D91, anim 0x41 hoist or 0x42 hoist_waist) and rate
(0x86D9E), X23's second landing (Step 2.127, AZ-572)."""
OVER_HOIST_HOOK = TrampolinePatch(
    name=f"{OVER_TOP_SHIM_NAME}_hoist",
    label=f"Player model hoist: its end onto the ledge's floor at a model scale (X23) at VA 0x{OVER_HOIST_HOOK_VA:X}",
    va=OVER_HOIST_HOOK_VA,
    replaced_bytes=_call(OVER_HOIST_HOOK_VA, 0x8C080),
    shim_object=OVER_TOP_SHIM.object_path(OVER_TOP_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_over_top",
)


def install_over_top_shim(xbe: bytearray, timers: bool = False) -> None:
    """Install X23 (``player_model/over_top.c``) at VA 0x87F65 in ``xbe``
    (either release) and, unless ``timers``, at the hoist's 0x86DAE
    (Step 2.127, AZ-572), one landing each: for the player's species
    gliding into climb_up_edge at a scale D other than 1, the glide starts
    (D - 1) x garret4's ``m_grab`` lower and ends (D - 1) x his ``m_feet``
    lower, where 0x41E50 scaled the start node and 0x42430 took off
    unscaled samples, so a baked body drawn at a model scale goes over the
    top with its drawn feet onto the floor, as x1's; into hoist or
    hoist_waist its end moves by (D - 1) x his ``m_feet`` at that clip's
    end, so the drawn feet end on the ledge's floor.  With ``timers`` (a
    body with no clips, whose root rides his ``m_feet`` / D, so the game's
    unscaled ends already put it at its entity: Step 2.127, AZ-562) only
    the ladder's start term, :data:`OVER_FEET_K` 0 (:func:`_install`)."""
    _install(xbe, OVER_TOP_HOOK, OVER_TOP_SHIM, "over the top", {OVER_FEET_K.name: 0.0 if timers else 1.0})
    if not timers:
        _install(xbe, OVER_HOIST_HOOK, OVER_TOP_SHIM, "over the top")


# --- X26: a baked body drawn at a model scale settles into its stance on the floor (Step 2.116) ---
STANCE_HOOK_VA = 0x42253
"""critter_model_matrix's (0x42200) CALL of the aligned-node term 0x402E0,
its only caller, which X26 replaces."""
STANCE_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="stance_term")
STANCE_SHIM_NAME = "player_model_stance_term"
"""Its object's name: ``player_model_stance_term.o`` in the shim build dir."""
STANCE_GLIDE_ON = FloatParam(
    name="stance_glide_on", symbol="_player_model_stance_glide_on", default=0.0,
    label="Player model stance: the climb-over's glide held (X26)",
    description="1: the climb-over's drawn lowest point is held no higher than the glide's end puts it.")
STANCE_GLIDE_END = FloatParam(
    name="stance_glide_end", symbol="_player_model_stance_glide_end", default=0.0,
    label="Player model stance: climb_up_edge's lowest bone at its end (X26)",
    description="The lowest bone of the clip the body plays as climb_up_edge at its end, over its origin, "
                "model units: where the glide's end puts the drawn lowest point (the top floor).")
STANCE_HOOK = TrampolinePatch(
    name=STANCE_SHIM_NAME,
    label=f"Player model stance: its hold at the drawn scale (X26) at VA 0x{STANCE_HOOK_VA:X}",
    va=STANCE_HOOK_VA,
    replaced_bytes=_call(STANCE_HOOK_VA, 0x402E0),
    shim_object=STANCE_SHIM.object_path(STANCE_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_stance_term",
    float_params=(STANCE_GLIDE_ON, STANCE_GLIDE_END),
)


def stance_glide_end(characters: bytes, body: Body) -> float | None:
    """X26's climb-over line (Step 2.175b, AZ-529 (c)): the lowest bone
    over its origin, model units, at the end of the clip ``body`` plays as
    climb_up_edge (a baked body's ``g4/climb_up_edge``, else its own),
    where X23's glide end puts its drawn feet on the top floor; None
    without one."""
    keys = {name.casefold(): i for i, name in named_resources(characters).items()}
    at = next((keys[k] for name in (f"{BAKED_DIR}climb_up_edge", "climb_up_edge")
               if (k := f"characters/{body.name}/{name}".casefold()) in keys), None)
    if at is None:
        return None
    clip = read_clip(characters, parse_toc(characters)[at].file_offset)
    return min(p[2] for p in origins(Rig.read(characters, body.name), clip, clip.length))


def install_stance_term_shim(xbe: bytearray, glide_end: float | None = None) -> None:
    """Install X26 (``player_model/stance_term.c``) at VA 0x42253 in
    ``xbe`` (either release), with X23 only and not on a body with no
    clips: for the player's species whose stance hold is on (move state
    0 right after climb_up_edge or a hoist (Step 2.127), with the aligned
    node m_feet and 0x402E0's term over 1 mm, kept in any state while both hold) the
    term is multiplied by the drawn scale, so after a ladder's top or a
    ledge the drawn body settles into its stance where X23 put it, its
    feet on the floor, instead of popping (D - 1) x garret4's ``m_feet``
    up; every other critter's term is the game's (:func:`_install`).
    With ``glide_end`` (:func:`stance_glide_end`) the climb-over's glide
    holds the drawn lowest point no higher than its end puts it (Step
    2.175b, AZ-529 (c))."""
    _install(xbe, STANCE_HOOK, STANCE_SHIM, "stance",
             {STANCE_GLIDE_ON.name: 0.0 if glide_end is None else 1.0,
              STANCE_GLIDE_END.name: 0.0 if glide_end is None else glide_end})


# --- the camera at any drawn size: the plan and X25's rig (Step 2.107, D280) ---
CAMERA_REST = 5.0
"""The level camera's rest distance from its point, m (0x19814C, which
the reset 0x811E0 gives a new level, a respawn and a warp), at -30
degrees (the pitch's)."""
CAMERA_EYE = 0.11
"""How far, m, the eye sits behind the camera's place along its view
(0x80B90's 0x19813C): the eye sees the point from 5.11 m at rest, and
the near plane is 0.11 m (0x198414)."""
CAMERA_PITCH = math.radians(30.0)
"""The camera's rest pitch under the horizon."""
CAMERA_TAN = fdlibm.tan(math.radians(35.0))
"""tan of half the projection's 70-degree horizontal field of view; the
vertical is 0.75 of it (4:3)."""
FRAME_EDGE = 0.95
"""How far out, in NDC, the drawn body's box may reach (:func:`frames`)."""
RIG_FLOOR = 0.1
"""The least rig scale (D 0.40 m, the camera 0.40 m over the point): a
floor on the camera's response, not on the body, which is drawn at any
finite scale (D23)."""
RIG_MIN = 0.005
"""X25 is installed when the rig scale is this far from 1 or farther."""
RIDE_CENTRE = 1.88
"""How far, m, under the zipline's cable the ride holds the player's
centre (+0x15C, garret4's collision at every scale), to which X20 raises
the camera's point: garret4's origin hangs 3.693 m under the cable and
his point 0.18 m over his centre [computed: sittings 2.105 and 2.106]."""
NEAR_RIG = 0.5
"""The rig scale under which X27 is installed: there the game's 1.0 m hide
round the player's collision centre (1.0 m over the drawn feet at any
size), at or over the drawn top, covers where the rig's eye rightly
orbits (computed: a garret4-shaped body's eye clears 1.5 m of it from s
0.32 at rest and 0.45-0.49 at the stick's steepest pitch)."""
POSE_REACH = 8.0
"""How many times its mesh top a body's posed reach must pass for the
camera to measure it by that pose (:func:`pose_top`; Step 2.116b, AZ-556):
the three water tentacles hold their bones risen, 12.4-19.5 x their bind
mesh's top over their idle (6 of water_tentacle3's 8 bones over the water
at rest, its camera inside the risen part); the next, key_air1-3 at 5.06 x,
ruby 4.72 x, the other gems and the power-ups 2.4-3.3 x, bob one bone with
no filed defect, and garret4's own swim pose reaches 1.21 x."""
POSE_SLOTS = (1, 70, 74)
"""The base clip slots whose clips :func:`pose_top` measures: idle and the
two swim slots (swim_idle, swim_2)."""
POSE_SAMPLES = 21
"""How many times over each clip's length :func:`pose_top` samples it."""
DRAWN_MIN = math.ldexp(1.0, -126)
"""The least drawn scale with a camera part: the game holds it (the
critter's +0x188) as a float32 and X8's swim divides by it, so one that
rounds to 0 or a denormal there (x1e-39, x1e-46) keeps the game's camera,
as 0 or less does."""


@dataclass(frozen=True)
class CameraShape:
    """What :func:`camera_plan` reads of a body (model units): its most
    detailed mesh's box (:func:`~azurik_mod.assets.characters.mesh_bounds`;
    no mesh, (0, 0, 0) to its bones' top), where its own ``m_head`` rests
    (``None``: it has none), and garret4's mesh top and eye height (m)."""

    low: tuple[float, float, float]
    high: tuple[float, float, float]
    head: float | None
    g4_top: float
    g4_eye: float
    posed: bool = False
    """Whether ``high``'s top is the body's posed reach (:func:`pose_top`),
    not its mesh's, so a body sized to garret4's height isn't framed as
    his mesh's height (:func:`camera_plan`)."""


def pose_top(characters_xbr: bytes, body: Body, fills: dict[int, tuple[str, float]] | None = None,
             held: Carriers | None = None) -> float:
    """The highest bone origin, model units over its origin, of the clips
    ``body``'s idle and swim slots (:data:`POSE_SLOTS`) play in the build:
    X11's fill (``fills``: a baked body's ``g4/`` clip, a stand-in), else
    its own clip of the slot's name, each at :data:`POSE_SAMPLES` times over
    its length (the engine model, :func:`~azurik_mod.assets.retarget.origins`);
    0 with none.  Bone origins only: the skinned mesh past the last joint
    isn't measured, nor a carried prop's bones (``held``, the build's
    :attr:`Loadout.carriers`)."""
    clips = {fills[s][0] if fills and s in fills else next(
        (c for c in body.clips if c.casefold() == BASE_CLIPS[s]), None) for s in POSE_SLOTS} - {None}
    keys = {name.casefold(): i for i, name in named_resources(characters_xbr).items()}
    at = [keys[k] for k in sorted(f"characters/{body.name}/{c}".casefold() for c in clips) if k in keys]
    if not at:
        return 0.0
    toc, rig, top = parse_toc(characters_xbr), Rig.read(characters_xbr, body.name), 0.0
    prop = carriers(rig, held)
    for i in at:
        motion = read_clip(characters_xbr, toc[i].file_offset)
        for k in range(POSE_SAMPLES):
            top = max(top, *(p[2] for j, p in enumerate(origins(rig, motion, motion.length * k / (POSE_SAMPLES - 1)))
                             if j not in prop))
    return top


def camera_shape(characters_xbr: bytes, body: Body, fills: dict[int, tuple[str, float]] | None = None,
                 held: Carriers | None = None) -> CameraShape:
    """``body``'s :class:`CameraShape` in ``characters_xbr``, its box's top
    raised to its posed reach (:func:`pose_top` with X11's ``fills`` and a
    carried prop's ``held`` bones) when
    that passes :data:`POSE_REACH` x its mesh's top (Step 2.116b, AZ-556:
    the water tentacles)."""
    low, high = mesh_bounds(characters_xbr, body.name) or ((0.0, 0.0, 0.0), (0.0, 0.0, body.top))
    head = marker_default(characters_xbr, body.name, CAMERA_MARKER)
    reach = pose_top(characters_xbr, body, fills, held) if body.clips and high[2] > 0.0 else 0.0
    posed = reach > POSE_REACH * high[2]
    return CameraShape(tuple(low), (high[0], high[1], reach) if posed else tuple(high), None if head is None else head[2],
                       height(characters_xbr, read_body(characters_xbr, PLAYER)), eye_height(characters_xbr), posed)


@dataclass(frozen=True)
class CameraPlan:
    """What a build does to the camera for a body (:func:`camera_plan`)."""

    aim: float | None
    """The camera point's height, model units: X8's ``eye_height``, or the
    body's own ``m_head`` (``None``: the game's, its feet)."""
    s: float
    """The rig scale: the drawn body's size over garret4's."""
    k_h: float
    """Its drawn height over garret4's."""
    margins: tuple[float, float]
    """X8's swim margins, m (:func:`swim_margins`; :data:`SWIM_MARGINS` without a rig)."""
    x8: bool
    lift: float
    """X19's lift (Step 2.104, AZ-520): how far, in metres, the drawn camera
    point sits above garret4's eye height (1.9925 m); X19 is installed from
    :data:`EYE_LIFT_MIN`."""
    x20: bool
    rig: bool
    """Whether X25 scales the level camera's rig by ``s``."""
    near: bool = False
    """Whether X27 draws the player's body however near the eye (``s``
    under :data:`NEAR_RIG`; Step 2.116, AZ-541)."""


def rest_distance(s: float) -> float:
    """The rig's rest distance, m, at scale ``s``: the eye 5.11 x ``s``
    from the point (:data:`CAMERA_REST` + :data:`CAMERA_EYE`, scaled),
    less the eye's 0.11 m behind the camera's place."""
    return (CAMERA_REST + CAMERA_EYE) * s - CAMERA_EYE


def swim_margins(s: float, least: float | None = None) -> tuple[float, float]:
    """X8's swim margins at rig scale ``s`` (m under the surface): the
    camera rises half its rest distance over the point, so these keep it
    at least max(2s, 0.6) m (``least`` m: a W27 body's
    :data:`SURFACE_FLOOR`, Step 2.150) over the surface on the top's side (its
    point the land point, raised to the first if need be: Step 2.116) and
    put it max(0.6, s) m under it once the top is under, at least 0.2 m clear of 0x81E10's
    0.4 m push band (at ``s`` 1, 0.5 and 3.5).  Both are garret4's x1
    ones scaled, so a pitch or distance the stick, RT or a slide gives
    keeps the camera on the body's side as far as it does his (the
    band 8.3 degrees of pitch or more off the rest's from s 1 up; under
    it the band's absolute 0.4 m narrows that)."""
    rise = 0.5 * rest_distance(s)
    return rise - (max(2.0 * s, 0.6) if least is None else least), rise + max(0.6, s)


def frames(low, high, drawn: float, point: float, s: float) -> bool:
    """Whether the rig at scale ``s`` frames a box (``low``, ``high``,
    model units) drawn at ``drawn`` and cut at its feet (z 0: what is
    under the floor isn't seen), from behind along the model's +y at -30
    degrees with the eye 5.11 x ``s`` from the point ``point`` m over the
    feet: every corner at least 0.11 + 0.1 x ``s`` m in front of the eye
    and inside :data:`FRAME_EDGE` of the frame (the projection's 70 degrees
    at 4:3)."""
    c, n = fdlibm.cos(CAMERA_PITCH), fdlibm.sin(CAMERA_PITCH)
    eye = (CAMERA_REST + CAMERA_EYE) * s
    ey, ez = -c * eye, point + n * eye
    near, wide, tall = CAMERA_EYE + 0.1 * s, FRAME_EDGE * CAMERA_TAN, FRAME_EDGE * 0.75 * CAMERA_TAN
    for x in (low[0], high[0]):
        for y in (low[1], high[1]):
            for z in (max(low[2], 0.0), max(high[2], 0.0)):
                vy, vz = y * drawn - ey, z * drawn - ez
                depth, up = vy * c - vz * n, vy * n + vz * c
                if depth < near or abs(x * drawn) > wide * depth or abs(up) > tall * depth:
                    return False
    return True


def camera_plan(shape: CameraShape, sized: float | None, drawn: float, model_scale: float,
                ride: float | None = None) -> CameraPlan:
    """The camera parts a build installs for a body of ``shape`` (Step
    2.107, D280; D115's default: framed as garret4 is at x1) drawn at
    ``drawn`` (the scale W2 writes, ``model_scale`` times the size's;
    ``sized`` the size garret4's scale, ``None`` at its own size; ``ride``
    how far its drawn origin hangs under the zipline's cable, m, X9's
    :func:`hang_scale` x garret4's grab, ``None`` unknown): X8's
    point at garret4's fraction of the drawn mesh top (his ``m_head`` over
    his mesh's top; sized and upright his eye height over ``sized``, the
    same point, but for a body measured by its pose, :attr:`CameraShape.posed`), on a body with a mesh top and no ``m_head`` resting at
    half its top or higher; the rig scale s, the drawn height over
    garret4's (``model_scale`` itself sized and upright), raised until the
    drawn box cut at its feet :func:`frames` at s and at least
    :data:`RIG_FLOOR`; X25 when s is :data:`RIG_MIN` from 1 or farther, its
    swim margins then :func:`swim_margins`'s, and X27 when s is under
    :data:`NEAR_RIG` (Step 2.116); X19's lift from the point;
    X20 on a body drawn taller than garret4, or one whose point rides under
    the centre (:data:`RIDE_CENTRE`: a body whose hang pose reaches far
    over its mesh, which Step 2.106 hangs by that top, the gems and the
    water tentacles; the sitting plan's F7), at x1 too since Step 2.118
    (AZ-536, D291: x1 hangs a shorter body by its top as well, so its
    drawn body no longer hangs a height under the cable).  A body drawn at a scale of
    0 or less (mirrored under its feet, or a point), at one the game's
    float32 holds as 0 or a denormal (:data:`DRAWN_MIN`) or as infinite,
    or with no top gets none of them: the game's camera."""
    low, high = shape.low, shape.high
    top = high[2]
    upright = top >= FLAT * max(h - lo for lo, h in zip(low, high))
    garret4s = sized is not None and upright and not shape.posed
    k_h = abs(model_scale) if garret4s else top * abs(drawn) / shape.g4_top
    try:
        held = struct.unpack("<f", struct.pack("<f", drawn))[0]   # as the game holds it
    except OverflowError:
        held = math.copysign(math.inf, drawn)
    if not (model_scale > 0.0 and DRAWN_MIN <= held < math.inf and top > 0.0):
        return CameraPlan(None, 1.0, k_h, SWIM_MARGINS, False, 0.0, False, False)
    x8 = shape.head is None or shape.head < 0.5 * top
    aim = (shape.g4_eye / sized if garret4s else shape.g4_eye / shape.g4_top * top) if x8 else shape.head
    s = max(k_h, RIG_FLOOR)
    if not frames(low, high, drawn, aim * drawn, s):
        least = s
        for _ in range(64):   # a box past what floats measure never fits: its farthest try stays (D23)
            s = 2.0 * least
            if frames(low, high, drawn, aim * drawn, s):
                break
            least = s
        for _ in range(60):
            mid = 0.5 * (least + s)
            least, s = (least, mid) if frames(low, high, drawn, aim * drawn, mid) else (mid, s)
    rig = abs(s - 1.0) >= RIG_MIN
    under = ride is not None and ride - aim * drawn > RIDE_CENTRE
    return CameraPlan(aim, s, k_h, swim_margins(s) if rig else SWIM_MARGINS, x8,
                      aim * drawn - shape.g4_eye, k_h > 1.0 or under, rig, s < NEAR_RIG)


def body_size(k_h: float) -> float:
    """The size s a body moves, rolls and touches at (Step 2.133; D330,
    D342, D344, D353, D356): its drawn height over garret4's
    (:attr:`CameraPlan.k_h`), exactly 1.0 within :data:`RIG_MIN` of it
    (X25's rule), so garret4 at x1 and a body standardized to his height
    keep his movement and their bytes."""
    return 1.0 if abs(k_h - 1.0) < RIG_MIN else k_h


@dataclass(frozen=True)
class SizeShape:
    """What a build's size reads of a body (:func:`size_shape`): its
    :class:`CameraShape` as the build dresses it, garret4's height's
    scale (``None``: its own size), the scale it is drawn at Model size 1,
    and whether its gameplay is garret4's exact (mode ``garret4``, Skin
    only), whose size is the Model size alone."""

    shape: CameraShape
    sized: float | None
    scale: float
    skin: bool = False


def size_shape(iso: Path, species: str, mode: str = DEFAULT_MODE, size: str = DEFAULT_SIZE,
               missing_anims: str | None = None, variant=None, weapon: str | None = None) -> SizeShape:
    """``species``' :class:`SizeShape` in the image ``iso`` as
    :func:`apply_player_model` would build it (garret4's own body: his,
    drawn x1): the body dressed by the build's own :func:`_dress` on a
    scratch staging of the image, so the size randomize-full folds into
    the movement sliders before its plan is the one the build's camera
    and touch use (2.133's critique, finding 2: X11's posed reach and
    W26's carried props move the drawn top), a ``variant`` (Step 2.137) with
    its recipe as the build dresses it, wearing ``weapon`` (Step 2.161b).
    :class:`ValueError` as the build's, for a species it can't use."""
    from azurkit.tools.characters.ports import IsoStaging

    scratch = IsoStaging(iso)
    check_player_model(scratch, species)
    if species == PLAYER:
        characters = scratch.stored("characters.xbr")
        return SizeShape(camera_shape(characters, read_body(characters, PLAYER)), None, 1.0)
    d = _dress(scratch, species, mode, missing_anims, size, variant=variant, weapon=weapon)   # at x1: only a clipless body's bake reads the
    sized, scale = body_scale(d.characters, d.body, d.theirs, mode, size)   # scale, and its shape reads no clip
    return SizeShape(camera_shape(d.characters, d.body, d.fills, d.loadout.carriers), sized,
                     1.0 if scale is None else scale,
                     mode == "garret4")


def movement_size(shape: SizeShape, model_scale: float) -> float:
    """The size s (:func:`body_size`) of a body of ``shape`` drawn
    ``model_scale`` times its size's scale: what randomize-full folds into
    the walk and roll sliders (``layer.size_params``) and X34's touch
    reads; in Skin only (mode ``garret4``, garret4's exact gameplay) the
    Model size alone, whatever the skin's own height (D115's default:
    keylord's skin is half his height)."""
    if shape.skin:
        return body_size(abs(model_scale))
    return body_size(camera_plan(shape.shape, shape.sized, shape.scale * model_scale, model_scale).k_h)


CAMERA_RIG = ((0x19814C, CAMERA_REST),   # the rest distance (the reset 0x811E0's): rest_distance(s)
              (0x198158, 0.5),           # the D-pad zoom's least (0x8190B)
              (0x19815C, 12.0),          # its most, the water push's reach (0x81CA3), RT's most (0xFB550's copy)
              (0x198160, 3.0),           # the most past the wanted distance (0x819DD)
              (0x198164, 10.0),          # the zoom rate and the regrow's cap (0x818F7, 0x81973)
              (0x198168, 10.0),          # the regrow per unit of stick (0x81969)
              (0x19816C, 2.0),           # the water push's least horizontal distance (0x81D3C)
              (0x198170, 6.0))           # RT's least (0x814B2)
"""X25's eight f32 constants (USA VA, vanilla value), each read only by
the camera module (0x80820-0x82680) or its boot copy (0xFB550): scaled by
the rig's s, the first to :func:`rest_distance`'s.  Not scaled: the
pitch and its clamps, the room's pitch, the field of view, the sweep
radius, the near plane, the push band and RT's +-2 zoom inputs."""
RIG_NOP_VA = 0x8196F
"""The regrow's ``fmul dword ptr [esp+0x20]`` (the stick deflections'
sum) in 0x81952-0x81A04, which X25 makes 4 NOPs, so a camera pulled in
regrows toward its wanted distance at 10 x s m/s (0x198164's cap) with no
stick held, as it does while one is."""
RIG_SITES = tuple(Site(va, pack_f32(v)) for va, v in CAMERA_RIG) + (
    Site(RIG_NOP_VA, bytes.fromhex("d84c2420")),)
"""X25's nine sites: the eight constants and the regrow's stick multiply."""


def install_camera_rig(xbe: bytearray, s: float) -> None:
    """X25 in ``xbe`` (either release; no shim): the level camera's
    metre-valued constants (:data:`CAMERA_RIG`) scaled by the rig scale
    ``s`` (:func:`camera_plan`), so it frames a body drawn ``s`` times
    garret4's size as it frames garret4 at x1, and the regrow's stick
    multiply (:data:`RIG_NOP_VA`) NOPed, so a camera that geometry pulled
    in regrows at rest at 10 x ``s`` m/s once the slide lets it.  A site
    that doesn't hold vanilla's bytes raises :class:`ValueError` naming
    it before anything is written (D27, D35)."""
    writes = []
    for site, value in zip(RIG_SITES, (rest_distance(s), *(v * s for _, v in CAMERA_RIG[1:]), None)):
        _, off, vanilla = xbe_site(xbe, site.va, site.original)
        if bytes(xbe[off:off + len(vanilla)]) != vanilla:
            raise ValueError(f"X25: VA 0x{site.va:X} doesn't hold vanilla's camera "
                             f"{'regrow' if value is None else 'constant'}; rebuild from vanilla")
        writes.append((off, b"\x90" * len(vanilla) if value is None else pack_f32(value)))
    for off, data in writes:
        xbe[off:off + len(data)] = data


# --- X27: a tiny player body is drawn with the camera near its centre (Step 2.116, AZ-541) ---
NEAR_CVAR_VA = 0x380E04
"""The "movie mode" cvar record's pointer (USA; Europe 0x382DA4), whose +4
the critter draw 0x3EA00 tests before its near hide."""
NEAR_CVAR = BytesParam(
    name="movie_cvar", symbol="_player_model_movie_cvar", size=4,
    label="Player model near draw: the movie-mode cvar (X27)")
"""X27's cvar address, four bytes: the abs32 of the build's own vanilla
load at 0x3EA57 (:func:`install_near_draw_shim`), so a Europe build reads
Europe's."""
NEAR_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="near_draw")
NEAR_SHIM_NAME = "player_model_near_draw"
"""Its object's name: ``player_model_near_draw.o`` in the shim build dir."""
NEAR_HOOKS = tuple(TrampolinePatch(
    name=name,
    label=f"Player model near draw: {what} (X27) at VA 0x{va:X}",
    va=va,
    replaced_bytes=bytes.fromhex(load) + struct.pack("<I", NEAR_CVAR_VA) + bytes.fromhex(flag),
    shim_object=NEAR_SHIM.object_path(NEAR_SHIM_NAME, CHECKOUT),
    shim_symbol=symbol,
    bytes_params=(NEAR_CVAR,),
) for name, what, va, load, flag, symbol in (
    (NEAR_SHIM_NAME, "the player drawn within 1 m", 0x3EA57, "8b15", "8b4204", "_c_player_model_near_draw"),
    (f"{NEAR_SHIM_NAME}_fade", "the player unfaded within 1.5 m", 0x3EC58, "8b0d", "8b4904",
     "_c_player_model_near_fade")))
"""X27's two hooks, the critter draw's (0x3EA00) loads of the movie-mode
flag (mov edx, [cvar]; mov eax, [edx + 4] and mov ecx, [cvar]; mov ecx,
[ecx + 4]: 9 bytes each, the cvar an abs32 at +2), one landing each."""


def install_near_draw_shim(xbe: bytearray) -> None:
    """Install X27 (``player_model/near_draw.c``) at VAs 0x3EA57 and
    0x3EC58 in ``xbe`` (either release), each with the cvar address its
    own vanilla load at 0x3EA57 holds: the critter draw's movie-mode flag
    reads 1 for the player, so its body skips the game's hide with the
    eye within 1.0 m of its collision centre and the fade to 1.5 m, and is
    drawn opaque; every other critter's is the game's (:func:`_install`)."""
    hook = NEAR_HOOKS[0]
    _, off, _ = xbe_site(xbe, hook.va, hook.replaced_bytes)
    cvar = bytes(xbe[off + 2:off + 6])
    for hook in NEAR_HOOKS:
        _install(xbe, hook, NEAR_SHIM, "near draw", {NEAR_CVAR.name: cvar})


# --- X29: a water push never leaves a tiny body's camera under its point (Step 2.116b, AZ-556) ---
PUSH_HOOK_VA = 0x81FEB
"""The level camera's water push (0x81E10): its first candidate's CALL of
camera_reach (0x81DB0), which X29 replaces (Europe 0x81F9B -> 0x81D60)."""
PUSH_SHIM = ShimSource(folder=ROLL_SHIM.folder, stem="water_push")
PUSH_SHIM_NAME = "player_model_water_push"
"""Its object's name: ``player_model_water_push.o`` in the shim build dir."""
PUSH_HOOK = TrampolinePatch(
    name=PUSH_SHIM_NAME,
    label=f"Player model camera: a water push keeps it over its point (X29) at VA 0x{PUSH_HOOK_VA:X}",
    va=PUSH_HOOK_VA,
    replaced_bytes=_call(PUSH_HOOK_VA, 0x81DB0),
    shim_object=PUSH_SHIM.object_path(PUSH_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_water_push",
)


LATCH_HOOK_VA = 0x81BEA
"""The level camera's (0x81240) CALL of its water push (0x81E10,
``camera_water_push``), once a tick, which X29's latch entry replaces
(Step 2.116e, R1; Europe 0x81B9A -> 0x81DC0)."""
LATCH_HOOK = TrampolinePatch(
    name=f"{PUSH_SHIM_NAME}_latch",
    label=f"Player model camera: a water push doesn't latch it at rest (X29) at VA 0x{LATCH_HOOK_VA:X}",
    va=LATCH_HOOK_VA,
    replaced_bytes=_call(LATCH_HOOK_VA, 0x81E10),
    shim_object=PUSH_SHIM.object_path(PUSH_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_push_latch",
)
EASE_HOOK_VA = 0x81891
"""The level camera's pitch ease's dt multiply, ``fmul dword ptr
[esp+0xbc]`` (7 bytes), which X29's ease entry replaces (Step 2.116e,
R1; Europe 0x81841); 0x81887's jump lands on its first byte."""
PUSH_HOLD_AT = BytesParam(
    name="push_hold_at", symbol="_player_model_push_hold_at", size=4,
    label="Player model water push: the latch landing's hold (X29)")
"""The ease landing's pointer to the latch landing's hold (each hook
lands its own copy of ``water_push.c``): its VA, four bytes."""
EASE_HOOK = TrampolinePatch(
    name=f"{PUSH_SHIM_NAME}_ease",
    label=f"Player model camera: a held pitch eases back at rest (X29) at VA 0x{EASE_HOOK_VA:X}",
    va=EASE_HOOK_VA,
    replaced_bytes=bytes.fromhex("d88c24bc000000"),   # fmul dword ptr [esp + 0xbc]
    shim_object=PUSH_SHIM.object_path(PUSH_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_push_ease",
    bytes_params=(PUSH_HOLD_AT,),
)


def install_water_push_shim(xbe: bytearray) -> None:
    """Install X29 (``player_model/water_push.c``) at VAs 0x81FEB, 0x81BEA
    and 0x81891 in ``xbe`` (either release), with X27: when the water
    push's far-side candidate would put the player's camera under its
    point and its own side keeps it over, the two swap, so the game sweeps
    its own side first (the far side its fallback) and the re-aim keeps
    the camera looking down at the body, as garret4's; and (Step 2.116e,
    R1) at rest (on the ground or swimming) the wanted pitch and distance
    a push latched are written back to what another writer last asked
    for (the reset's -30 deg and D(s), the player's stick or zoom) and the
    pitch eases back at the game's 30 deg/s (snapped after a hoist out of
    the water), except while the place the camera would rest at is inside
    the push's own band (the game's volume query there), where the game's
    latch stays; every other camera's push is the game's
    (:func:`_install`)."""
    _install(xbe, PUSH_HOOK, PUSH_SHIM, "water push")
    _install(xbe, LATCH_HOOK, PUSH_SHIM, "water push latch")
    at = trampoline_symbol_va(xbe, LATCH_HOOK, "_player_model_push_hold", CHECKOUT,
                              shim_source=PUSH_SHIM.source_path())
    _install(xbe, EASE_HOOK, PUSH_SHIM, "water push ease", {PUSH_HOLD_AT.name: struct.pack("<I", at)})


# --- W19: own body's combo chains inside the stun (Step 2.104, AZ-496) ------
CHAINED = ("basic1", "basic2", "basic3")
"""The columns whose next move needs a stunned (or frozen) target ahead:
``attacks_transitions``' rows 28-31 (basic1 -> basic2 -> basic3 ->
finish, finish3), searched by 0x7EF10 from the chain check 0x8D452."""
CHAIN_AFTER_HIT = 0.2
"""W19: how long after a basic's first damage tick, in seconds, own body's
chain point comes (D115's default): a light hit stunned a keylord 10-28
ticks in sitting 2.103 (the control's 5-81), and garret4's basic1 and
basic2 chain 5.3 and 6.8 ticks after their first hit [computed]."""


STUN_LAG = 4 / 30
"""W19 (Step 2.105, AZ-495): the least time, in seconds, a chain comes after
its swing's box first meets the target ahead: a hit's stun shows 3 ticks
later (sitting 2.104), and a tick more (D115's default)."""
STUN_TICKS = 3
"""Ticks from a hit's tick to the first on which its target shows the stun
(sitting 2.104), which a chain check on that tick sees (sitting 2.189a)."""


def stun_point(hit: float) -> float:
    """The earliest chain point, in seconds into a move, whose chain check
    sees the stun of its hit at ``hit`` seconds into it (Step 2.189a,
    AZ-712): the game deals the hit on the tick its clip time passes
    ``hit`` and checks the chain on the tick it passes the point (sitting
    2.189a: the model's 2.5 and 5.13 ticks were swing ticks 2 and 6; a hit
    on a tick's edge, sitting 2.175a's 10.00, played on tick 9 every time),
    :data:`STUN_TICKS` later, half a tick in, clear of a tick's edge (a
    point on one chained a tick early once in 9)."""
    return (math.ceil(30.0 * hit - 1e-6) - 1 + STUN_TICKS + 0.5) / 30.0


TARGET_AHEAD = (0.35 * 2.0, 2.8)
"""The target W19 times a chain on (D115's default, Step 2.105): a keylord
(``collisionRadius`` 0.35 at its ``scale`` 2, 2.8 m tall), the e7
sittings' target, standing against the player dead ahead."""
PLAYER_RADIUS = 0.5
"""garret4's ``collisionRadius``, the player's move query's radius at every
drawn scale (0x8570D takes 0.5 from 0x1A9C84, unscaled): W19's contact
stands the target this far ahead of a body drawn at 1 or less, and
:data:`PLAYER_RADIUS` × D ahead of one drawn larger (D296, Step 2.118,
AZ-537), since an enemy's own sweep may see the player's radius × D
(0x418B0 takes a critter's radius × its +0x188: unread whether it stops
there)."""


def contact(characters_xbr: bytes, owner: str, clip: str, drawn: float, clip_length: float,
            window: tuple[float, float], reach: float = 1.0, fill: bool = False) -> float | None:
    """When, in clip seconds, the move playing ``owner``'s ``clip`` (its
    ``clip_length``) from ``window[0]`` to ``window[1]`` of it, drawn at
    ``drawn``, first meets :data:`TARGET_AHEAD` against the player
    (:func:`~azurik_mod.assets.characters.first_contact`, its boxes
    ``reach`` times as X13 grows them and, with ``fill``, filled as X13
    fills them in its column: Step 2.132, AZ-605; lowered, Step 2.106,
    AZ-534); ``None`` when it never does."""
    return first_contact(characters_xbr, owner, clip, drawn, PLAYER_RADIUS * max(drawn, 1.0), *TARGET_AHEAD,
                         reach=reach, span=(window[0] * clip_length, window[1] * clip_length), fill=fill)


def _chain_at(rate: float, clip: float, window: tuple[float, float],
              windows: tuple[DamageWindow, ...] | None, met: float | None) -> tuple[float, float, float]:
    """A move's first damage tick, its contact with the target ahead
    (``met`` clip seconds, else that tick) and W19's chain point, each in
    seconds into the move at ``rate`` (:func:`chain_fraction`)."""
    hit = windup(rate, clip, window, windows)
    touch = hit if met is None else max(hit, (met - window[0] * clip) / rate)
    return hit, touch, max(hit + CHAIN_AFTER_HIT, touch + STUN_LAG)


def chain_fraction(rate: float, clip: float, window: tuple[float, float],
                   windows: tuple[DamageWindow, ...] | None, met: float | None = None) -> float | None:
    """W19's chain point for a move playing a ``clip``-second clip from
    ``window[0]`` to ``window[1]`` of it at ``rate`` with ``windows``
    (:func:`windup`; ``None`` X3's), as a fraction of the clip:
    :data:`CHAIN_AFTER_HIT` after its first damage tick, or
    :data:`STUN_LAG` after its box first meets the target ahead (``met``,
    clip seconds, :func:`contact`; ``None``, its first damage tick: X3's
    box, or a box that never meets it) if that is later (Step 2.105,
    AZ-495), never past ``window[1]``; ``None`` for a move that hits
    nothing."""
    start, end = window
    if rate <= 0 or clip <= 0 or end <= start or windows is not None and not any(
            min(w.off, end * clip) >= max(w.on, start * clip) for w in windows):
        return None
    return min(end, start + _chain_at(rate, clip, window, windows, met)[2] * rate / clip)


def chain_ticks(rate: float, clip: float, window: tuple[float, float],
                windows: tuple[DamageWindow, ...] | None, met: float | None = None) -> tuple[float, float] | None:
    """When, in ticks into the move (:func:`chain_fraction`'s), it first
    hits the target ahead (its first damage tick, or its box's contact
    ``met`` if later) and when W19 chains out of it (Step 2.138, AZ-614:
    the swing the combo plays); ``None`` for a move that hits nothing."""
    at = chain_fraction(rate, clip, window, windows, met)
    if at is None:
        return None
    return 30.0 * _chain_at(rate, clip, window, windows, met)[1], 30.0 * (at - window[0]) * clip / rate


def chain_terms(clip: float, window: tuple[float, float],
                windows: tuple[DamageWindow, ...] | None, met: float | None = None) -> tuple[float, float] | None:
    """X10's ring entry's chain point (Step 2.104, AZ-523), whatever Rate
    the swing plays at: ``(hit, after)``, a move playing a ``clip``-second
    clip from ``window[0]`` to ``window[1]`` of it with ``windows``
    (:func:`windup`; ``None`` X3's) at a Rate r chaining at ``hit`` +
    ``after`` x r of the clip (:func:`chain_fraction` but for its cap at
    ``window[1]``, which the shim takes from the row's Move end2):
    ``hit`` its first damage tick, ``after`` :data:`CHAIN_AFTER_HIT` at
    Rate 1; or, where that comes before :data:`STUN_LAG` after its box
    first meets the target ahead at Rate 1 (``met``, :func:`contact`;
    Step 2.105, AZ-523), ``hit`` that contact and ``after``
    :data:`STUN_LAG`; ``None`` for a move that hits nothing."""
    start, end = window
    if clip <= 0 or end <= start or windows is not None and not any(
            min(w.off, end * clip) >= max(w.on, start * clip) for w in windows):
        return None
    hit, touch, _ = _chain_at(1.0, clip, window, windows, met)
    if hit + CHAIN_AFTER_HIT < touch + STUN_LAG:
        return start + touch / clip, STUN_LAG / clip
    return start + hit / clip, CHAIN_AFTER_HIT / clip


def chain_point(anims, col: int, clip: float, windows: tuple[DamageWindow, ...] | None,
                met: float | None = None) -> float | None:
    """W19's ``Move end1`` for ``attacks_anims`` column ``col`` playing a
    ``clip``-second clip at its ``Rate`` with ``windows``
    (:func:`windup`; ``None`` X3's) and its box first meeting the target
    ahead at ``met`` clip seconds (:func:`contact`; ``None``, never): the
    value whose fraction of the clip (0x7E2E0's reading, as
    :func:`move_window`'s; the chain check 0x8D452 lets a press chain
    from the tick the clip's fraction reaches it) comes at
    :func:`chain_fraction`'s point, never past Move end2; ``None`` to
    keep the column's: when its chain comes after the first hit, no
    sooner than :data:`STUN_LAG` after that contact and at most a tick
    later than the point, the move hits nothing, or a cell is missing."""
    name = anims.col_names()[col]
    value = {row: c.double_value if (c := anims.find_cell(name, row, col)) is not None and c.type_code == 1
             else None for row in ("Anim start", "Anim end", "Move end1", "Rate")}
    a0, a1, e1, rate = value["Anim start"], value["Anim end"], value["Move end1"], value["Rate"]
    window = move_window(anims, col)
    if None in (a0, a1, e1, rate) or a1 == a0:
        return None
    want = chain_fraction(rate, clip, window, windows, met)
    if want is None:
        return None
    hit, touch, at = _chain_at(rate, clip, window, windows, met)
    now = ((e1 - a0) / (a1 - a0) - window[0]) * clip / rate
    if hit < now <= at + 1 / 30 and (met is None or now >= touch + STUN_LAG):
        return None
    return a0 + want * (a1 - a0)


HIT_DELAY = 0.33
"""The player's damage types' ``Delay``, in seconds: the no-hit window a
hit that deals damage gives its target (0x43210; :data:`HIT_TICKS`),
which X31 divides by the attack speed above x1."""
FOLLOWS = {"basic1": ("basic2",), "basic2": ("basic3",), "basic3": FINISHERS}
"""The moves each basic chains into (``attacks_transitions``' rows 28-31)."""


def next_hit_ticks(speed: float) -> int:
    """How many ticks after a hit of the player's at ``speed`` its target
    takes the next: X31's window f32(f32(:data:`HIT_DELAY`) x f32(1 /
    speed)) above x1 (:func:`shortens_hit_delay`), the record's at or
    below, less 1/30 s each tick, 0x43210 dropping a hit while it is above
    0 (sitting 2.189a: x1.5's 0.22 s dropped basic2's hit 6 ticks after
    basic1's, 0.02 s left; x2's 0.165 let it land 5 after)."""
    def f32(x: float) -> float:
        return struct.unpack("<f", struct.pack("<f", x))[0]
    window = f32(f32(HIT_DELAY) * f32(1.0 / speed)) if shortens_hit_delay(speed) else HIT_DELAY
    return math.ceil(30.0 * window - 1e-6)


def follow_hit(anims, col: int, move) -> float | None:
    """The first damage, in seconds into it at its own ``Rate``, of the
    move ``attacks_anims`` column ``col`` (a basic) chains into
    (:data:`FOLLOWS`; the sooner finisher after basic3), ``move(j)`` giving
    column j's clip length and damage windows (:func:`windup`); ``None``
    where a column or its ``Rate`` is missing."""
    names = anims.col_names()
    hits = []
    for name in FOLLOWS.get(names[col], ()):
        j = names.index(name) if name in names else None
        cell = anims.find_cell(name, "Rate", j) if j is not None else None
        if cell is None or cell.type_code != 1 or cell.double_value <= 0:
            return None
        clip, windows = move(j)
        hits.append(windup(cell.double_value, clip, move_window(anims, j), windows))
    return min(hits, default=None)


def speed_chain(anims, col: int, clip: float, windows: tuple[DamageWindow, ...], speed: float,
                follow: float | None = None) -> float | None:
    """W14's chain rule on garret4's own table (Step 2.123, D312; Q2's
    default): the ``Move end1`` for ``attacks_anims`` column ``col`` (its
    vanilla cells; a basic, :data:`CHAINED`) playing his ``clip``-second
    clip with ``windows`` at ``speed`` times its ``Rate``: the time from
    its first damage tick to the chain, the clip's own at x1, divided by
    ``speed`` but held to at least :func:`stun_point` (the first tick the
    stun shows: Step 2.189a, AZ-712; :data:`STUN_LAG`'s tick more put
    basic1 at x2 a swing tick past the raw point's, and in same-state runs
    the later chain lost the combo more), or to :data:`STUN_LAG` where
    that would bring the next move's first damage (``follow``,
    :func:`follow_hit`) inside the no-hit window this move's hit gave its
    target (:func:`next_hit_ticks`; sitting 2.189a: x1.5's basic1 a tick
    sooner, basic2 dealt damage 6 times of 36, main's 33 of 33), and at most its x1 time
    (the stun still holds), never past the move's end; ``None`` where that
    is the cell's own value (for basic1 from x1 to about x2, but x1.6, by
    the tick grid), at a ``speed`` of 0 or less (the move never ends: D23,
    nothing clamped), a move that hits nothing, or a cell that is
    missing."""
    name = anims.col_names()[col]
    value = {row: c.double_value if (c := anims.find_cell(name, row, col)) is not None and c.type_code == 1
             else None for row in ("Anim start", "Anim end", "Move end1", "Rate")}
    a0, a1, e1, rate = value["Anim start"], value["Anim end"], value["Move end1"], value["Rate"]
    start, end = window = move_window(anims, col)
    if None in (a0, a1, e1, rate) or a1 == a0 or speed <= 0 or rate <= 0 or clip <= 0 or end <= start or not any(
            min(w.off, end * clip) >= max(w.on, start * clip) for w in windows):
        return None
    hit = windup(rate, clip, window, windows)   # seconds into the move at x1
    gap = ((e1 - a0) / (a1 - a0) - start) * clip / rate - hit
    if gap <= 0:
        return None
    def chain_at(held: float) -> float:
        return min(hit / speed + min(max(gap / speed, held), gap), (end - start) * clip / rate / speed)

    def tick(t: float) -> int:
        return math.ceil(30.0 * t - 1e-6)
    chain = chain_at(stun_point(hit / speed) - hit / speed)
    if follow is not None and tick(chain) + tick(follow / speed) - tick(hit / speed) < next_hit_ticks(speed):
        chain = chain_at(STUN_LAG)
    frac = start + chain * rate * speed / clip
    return None if math.isclose(frac, (e1 - a0) / (a1 - a0), rel_tol=0.0, abs_tol=1e-9) else a0 + frac * (a1 - a0)


def chains_early(anims, col: int, clip: float, windows: tuple[DamageWindow, ...] | None,
                 met: float | None = None) -> bool:
    """Whether ``attacks_anims`` column ``col``'s own ``Move end1`` lets a
    press chain out of its move playing a ``clip``-second clip with
    ``windows`` (:func:`windup`; ``None`` X3's) before the move touches
    the target ahead: its first damage tick, or its box's first contact
    with it (``met`` clip seconds, :func:`contact`) where that is later
    (Step 2.106, AZ-495: guard_air own's right1 chained into basic1 at 18
    ticks, its hit at 36.66); clip times, so at any Rate.  ``False`` for a
    move that hits nothing or a cell that is missing."""
    name = anims.col_names()[col]
    value = {row: c.double_value if (c := anims.find_cell(name, row, col)) is not None and c.type_code == 1
             else None for row in ("Anim start", "Anim end", "Move end1")}
    a0, a1, e1 = value["Anim start"], value["Anim end"], value["Move end1"]
    window = move_window(anims, col)
    if None in (a0, a1, e1) or a1 == a0 or chain_fraction(1.0, clip, window, windows, met) is None:
        return False
    _, touch, _ = _chain_at(1.0, clip, window, windows, met)
    return ((e1 - a0) / (a1 - a0) - window[0]) * clip < touch


def planted_chain(anims, transitions, plant: tuple[float, float], turns: float,
                  hold: float) -> tuple[float, float, bool]:
    """W37 (Step 2.180, D701, the owner: "after each spin she instantly gets
    up and then instantly goes back into the next spin in the chain"): B's
    chain of a hand spin that sweep1 and sweep2 both play
    (:meth:`~azurik_mod.patches._player_variants.Variant.loop`) stays
    planted, ``plant`` its plant (clip fractions), ``turns`` its turns and
    ``hold`` its rest on the hand after them.  The game starts a chained clip at its Move start
    (0x88990) and chains the next press on any tick from Move end1 to the
    clip's end mark (0x8D452), each a fraction of the clip as 0x7E2E0
    reads it (Anim start and end: 0 and 1 if empty), a press under 0.3 s
    old (0x88A80); vanilla's sweep2 has no Move cells, so it played from its
    clip's standing start and chained only after its rise, and its B press
    went back to sweep1 (row 36), which starts standing too.  Both B
    columns' Move end1 becomes the rest's start ``e`` (``plant[1]`` -
    ``hold``: her turns done), and sweep2's Move start ``s`` one turn
    before it, the same planted pose, so a press up to 0.3 s before ``e``
    or any time in the rest chains her on from one pose (the skeptic's R1:
    with sweep2 chaining as her turn went on, a press 4-6 ticks after it
    cut her from a half-rise, 0.9-1.3 m, back down); its Move end2 the
    clip's end (the rise plays as the chain ends); ``attacks_transitions``
    row 33 (B near a cliff: sweep ledge) becomes sweep2's B -> sweep2, so
    the chain loops sweep2, and row 27 (B from a run: sweep2) plays
    sweep1, which eases down from the run.  Returns (``s``, ``e``,
    whether sweep1's chain point moved); :class:`XbrStructuralError` for a
    row that isn't vanilla's (D27)."""
    names = anims.col_names()

    def scale(col: str) -> tuple[float, float]:
        i = names.index(col)
        return tuple(c.double_value if (c := anims.find_cell(col, row, i)) is not None and c.type_code == 1 else empty
                     for row, empty in (("Anim start", 0.0), ("Anim end", 1.0)))
    one, two = names.index("sweep1"), names.index("sweep2")
    (a0, a1), (b0, b1) = scale("sweep1"), scale("sweep2")
    end1 = anims.find_cell("sweep1", "Move end1", one)
    f = (end1.double_value - a0) / (a1 - a0) if end1 is not None and end1.type_code == 1 else 1.0
    e = plant[1] - hold
    s = e - e / abs(turns)
    if e != f:
        set_keyed_double(anims, "sweep1", "Move end1", a0 + e * (a1 - a0), col=one, fill_empty=True)
    for row, at in (("Move start", s), ("Move end1", e), ("Move end2", 1.0)):
        set_keyed_double(anims, "sweep2", row, b0 + at * (b1 - b0), col=two, fill_empty=True)
    cols = transitions.col_names()

    def text(c: int, row: str) -> str | None:
        cell = transitions.find_cell(cols[c], row, c)
        return cell.string_value if cell is not None and cell.type_code == 2 else None

    def only(what: str, test) -> int:
        found = [c for c in range(len(cols)) if test(c)]
        if len(found) != 1:
            raise XbrStructuralError(f"W37: attacks_transitions has {len(found)} rows {what}, vanilla's one: rebuild "
                                     "from vanilla")
        return found[0]
    ledge = only("playing sweep ledge", lambda c: text(c, "next move") == "sweep ledge" and text(c, "last move") is None)
    run = only("from a run to sweep2", lambda c: (text(c, "last move"), text(c, "next move")) == ("run", "sweep2"))
    chain = only("from sweep1 to sweep2", lambda c: (text(c, "last move"), text(c, "next move")) == ("sweep1", "sweep2"))
    fresh = only("from none to sweep1", lambda c: text(c, "next move") == "sweep1" and text(c, "last move") is None)
    held = transitions.find_cell(cols[chain], "next move", chain)
    point_keyed_string(transitions, cols[ledge], "last move", cols[chain], "next move", col=ledge, src_col=chain,
                       fill_empty=True, src_cell=held)
    point_keyed_string(transitions, cols[ledge], "next move", cols[chain], "next move", col=ledge, src_col=chain,
                       src_cell=held)
    clear_keyed_cell(transitions, cols[ledge], "near cliff", col=ledge)
    point_keyed_string(transitions, cols[run], "next move", cols[fresh], "next move", col=run, src_col=fresh)
    return s, e, e != f


SHIMS = ((ROLL_HOOK, ROLL_SHIM), (DAMAGE_MARKER, DAMAGE_MARKER_SHIM), (HIT_HOOK, HIT_SHIM),
         (SLOTS_HOOK, SLOTS_SHIM), *((hook, BORROW_SHIM) for hook in BORROW_HOOKS),
         (BORROW_FIRST, BORROW_FIRST_SHIM), (EYE_HOOK, EYE_SHIM),
         *((hook, CLIMB_SHIM) for hook in (*CLIMB_HOOKS, CLIMB_OFFSETS_HOOK)), (ROTATE_HOOK, ROTATE_SHIM),
         (ATTACK_BOX_HOOK, ATTACK_BOX_SHIM), *((hook, SOUNDS_SHIM) for hook in SOUND_HOOKS),
         (WINGS_BIND, WINGS_SHIM), (WINGS_POSE, WINGS_SHIM), (LIGHT_HIT_HOOK, LIGHT_HIT_SHIM),
         (HIT_DELAY_HOOK, HIT_DELAY_SHIM), (HIT_FX_HOOK, HIT_FX_SHIM), (THUD_HOOK, THUD_SHIM), (THROW_HOOK, THROW_SHIM),
         (CARRY_HOOK, CARRY_SHIM),
         *((hook, CARRY_SHIM) for hook in CARRY_ENTRIES),
         (EYE_SWEEP_HOOK, EYE_SWEEP_SHIM), (EYE_SIGHT_HOOK, EYE_SWEEP_SHIM),
         (EYE_REGROW_HOOK, EYE_SWEEP_SHIM), (EYE_HANG_HOOK, EYE_HANG_SHIM), (SEARCH_HOOK, SEARCH_SHIM),
         *((hook, HANG_EASE_SHIM) for hook in (*HANG_EASE_HOOKS, HANG_EASE_GROUND)),
         *((hook, HOLD_SHIM) for hook in HOLD_HOOKS),
         (OVER_TOP_HOOK, OVER_TOP_SHIM), (OVER_HOIST_HOOK, OVER_TOP_SHIM),
         (STANCE_HOOK, STANCE_SHIM), (FADE_HOOK, FADE_SHIM), *((hook, NEAR_SHIM) for hook in NEAR_HOOKS),
         *((hook, PUSH_SHIM) for hook in (PUSH_HOOK, LATCH_HOOK, EASE_HOOK)), (TOUCH_HOOK, TOUCH_SHIM),
         *((hook, SETS_SHIM) for hook in SETS_HOOKS), *((hook, DRAIN_SHIM) for hook in DRAIN_HOOKS),
         *((hook, FX_RING_SHIM) for hook in FX_RING_HOOKS), (FX_DEFAULT_HOOK, FX_DEFAULT_SHIM),
         *((hook, BLAST_SHIM) for hook in BLAST_HOOKS), (JIGGLE_HOOK, JIGGLE_SHIM), (IDLE_HOOK, IDLE_SHIM),
         (CANCEL_HOOK, CANCEL_SHIM), (BODY_KEY_HOOK, BODY_KEY_SHIM), (SEEK_HOOK, SEEK_SHIM),
         (FINISH_RANGE_HOOK, FINISH_RANGE_SHIM))
"""Each shim's hook and source (X4, X3, X7, X11, X12's hooks, X44, X8, X9's
seven, X10, X13, X14's two, X16's two, X18, X31, X32, X43, X42, X33's seven, X19's three, X20, X21, X22's
four, X28's three, X23's two, X26, X48, X27's two, X29's three, X34, X36's two, X37's three, X38's three, X40,
X39's four, X41, X45, X46, X47, X49, X50)."""
SHIM_HOOKS = {hook.va: hook.replaced_bytes for hook, _ in SHIMS}
"""Each shim hook's VA (X4, X3, X7, X11, X12 and X44, X8, X9, X10, X13, X14, X16, X18, X31, X32, X43, X42, X33, X19, X20, X21, X22, X28, X23, X26,
X48, X27, X29, X34, X36, X37, X38, X40, X39, X41, X45, X46, X47, X49, X50) -> the vanilla bytes it replaces (a CALL, or a longer run such as X12's six at 0xCAEC0, X18's ten at
0x30C1C, X20's ten at 0x81292, X31's nine at 0x43584, X34's thirteen at 0x8C553, X46's six at 0x8CF84 and X50's
eight at 0x7F0B2);
``verify-patches --strict`` declares a hook where it calls a shim
(AZ-292)."""
XBE_SITES = (*((hook.name, hook) for hook, _ in SHIMS), *((f"X15 {site.sound}", site) for site in XBE_SOUND_SITES),
             ("X17", STAFF_WALLS), ("X30", STAFF_X1), *(("X36", spec) for spec in DIRECTION_EDITS),
             ("W40", FINISH_RANGE), *(("X21", site) for site in SEARCH_SITES), *(("X25", site) for site in RIG_SITES))
"""Every vanilla span of ``default.xbe`` the swap writes, each with what
writes it (a shim hook's name, else its X or W number): the spans
``verify-patches --strict`` reads of a swap build, Europe's address map
covers (``tests/test_region.py``) and the facts record (Step X.101)."""
HANDED_VAS = {CLIMB_SHIM_NAME: CLIMB_OFFSETS, SETS_SHIM_NAME: (HUD_MATERIAL_VA,),
              BORROW_OBJECT: (ANIM_CHANGE_CALL + 5,), IDLE_OBJECT: struct.unpack_from("<I", IDLE_TIMER_LOAD, 2),
              JIGGLE_SHIM_NAME: struct.unpack_from("<I", JIGGLE_SCENE_LOAD, 2), NEAR_SHIM_NAME: (NEAR_CVAR_VA,),
              FADE_SHIM_NAME: (FADE_CAMERA_VA + 5,)}
"""The vanilla addresses the build writes into a shim's data, as the
release has them, for it to read or call (X9's ladder offset arrays, X36's
2D material, X12's return from anim_change's clip change, X45's standing
timer, X41's scene global, X27's movie-mode cvar, the crossfade floor's
return from the camera point's call), by the shim's object name; every
other vanilla address a shim calls it links by its vanilla-symbol registry
name."""


def install_sounds_shim(xbe: bytearray, roles: SoundRoles) -> None:
    """Install X14 (``player_model/sounds.c``) at VAs 0x4B93C and 0x7E3DD
    in ``xbe``, one landing per hook, each with ``roles``' table
    (:func:`~azurik_mod.patches._player_sounds.sound_table`): the
    player's species binds each slot of the table from the model's sound
    dir, and every other slot and species as before (:func:`_install`)."""
    table = sound_table(roles)
    for hook in SOUND_HOOKS:
        _install(xbe, hook, SOUNDS_SHIM, "sounds", {SOUNDS_TABLE.name: table})


def model_sounds(files, species: str) -> SoundRoles:
    """``species``' sounds as its swap binds them (``files``: a mapping
    of ``config.xbr``, ``characters.xbr``, ``fx.xbr`` and ``english.xbr``
    to bytes): its attacks play the clips W3 picks (:func:`substitutes`),
    or garret4's when its body has none."""
    config = XbrDocument.from_bytes(bytes(files["config.xbr"]))
    body = read_body(bytes(files["characters.xbr"]),
                     _species(config.keyed_section("critters_engine"))[species]["body"])
    columns = config.keyed_section("attacks_anims").col_names()
    picks = dict(zip(columns, substitutes(columns, body))) if body.clips else None
    return sound_roles(files, species, picks)


def install_hit_shim(xbe: bytearray) -> None:
    """Install X7 (``player_model/hit_reaction.c``) at VA 0x8D682 in
    ``xbe``: every hit reaction the chooser 0x30BD0 picks (anim 37-42)
    plays the body's ``ouch_1``, else its ``idle``, else the roll's clip,
    at the rate that ends it in garret4's 0.4 s (AZ-291: on the ground
    the player has no control until it ends), with every other anim
    layer freed at once (AZ-304: a layer fading out kept its clip
    running into its damage window; :func:`_install`)."""
    _install(xbe, HIT_HOOK, HIT_SHIM, "hit-reaction", {HIT_SECONDS.name: HIT_SECONDS.default})


def shim_data(xbe: bytes) -> list[tuple[int, int]]:
    """The ``[start, end)`` VAs the player-model shims in ``xbe`` write
    while the game runs: their landed ``.data`` and ``.bss``
    (:func:`~azurik_mod.patching.apply.trampoline_shim_data`), X3's
    damage marker and the body's own it keeps in a build that carries X3
    (AZ-300), X10's ring.  A guest running
    ``xbe`` differs from its ``SHIMS`` there; ``[]`` for a build with
    none of these shims.  Where two shims share a hook (X12's attack hook
    and X44 at 0x7E3F0) the one the build landed counts, and the other's
    object not matching the code there is no error (AZ-688);
    :class:`ValueError` when no shim at a hook matches it."""
    spans, landed, errors = [], set(), {}
    for hook, shim in SHIMS:
        try:
            spans += trampoline_shim_data(xbe, hook, CHECKOUT, shim_source=shim.source_path())
            landed.add(hook.va)
        except ValueError as error:
            errors.setdefault(hook.va, error)
    for va, error in errors.items():
        if va not in landed:
            raise error
    return sorted(spans)


def check_player_model(game, species: str) -> None:
    """Raise :class:`ValueError` naming why ``species`` can't dress the
    player in ``game``'s files (an
    :class:`~azurik_mod.patching.xbr_staging.IsoStaging`), before a build
    starts (D35)."""
    engine = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("critters_engine")
    why = _refusal(_species(engine), body_names(game.stored("characters.xbr")), species)
    if why:
        raise ValueError(f"--player-character {species!r}: {why}")


def mode_status(species: str, mode: str = DEFAULT_MODE, size: str = DEFAULT_SIZE,
                model_scale: float = 1.0) -> tuple[str, str]:
    """``species``' status and why in gameplay ``mode`` at ``size`` (Steps
    2.74, 2.75), drawn ``model_scale`` times it (another build than any
    sitting graded unless 1.0, so unseen but for an untested item: Step
    2.98, D242): its grade from a sitting of that build
    (:data:`MODE_GRADES`), or of the partner whose ISO it builds there
    (:data:`MODE_SHARES`: Q262, D242, AZ-492; a share that differs only
    in the species' own sounds says so), else :data:`UNSEEN` (D242,
    since Step 2.75b's sitting S4: :data:`SUPPORT`'s grades came from
    builds no mode makes exactly, Step 2.65), but red "untested" in
    garret4's exact and own body for a species :data:`SUPPORT` doesn't
    hold, graded on nothing.  garret4 at x1 writes nothing, so its
    status is the same in every mode; drawn at another size (Step 2.123)
    he is :data:`GARRET4_SIZES`' grade where a sitting graded that size,
    else unseen too."""
    if model_scale != 1.0:
        if species == PLAYER and model_scale in GARRET4_SIZES:
            return GARRET4_SIZES[model_scale]
        graded = mode_status(species, mode, size)
        return graded if graded == UNTESTED else (
            "unseen", f"no sitting has graded its build drawn x{model_scale:g} its size (D242)")
    if species == PLAYER:
        return status(species)
    grades = MODE_GRADES[mode, size]
    if species in grades:
        return grades[species]
    partner, _, sounds_only = MODE_SHARES[mode, size].get(species, ("", "", False))
    if partner in grades:
        colour, why = grades[partner]
        same = ("but for its own sounds (with Garret's, byte for byte; a species' own sounds aren't on the "
                "checklist, Step 2.72)" if sounds_only else "byte for byte")
        return colour, f"builds the same ISO as {partner} in this mode, {same}, so it carries its grade (Q262): {why}"
    return UNSEEN if species in SUPPORT else UNTESTED


def _doubles(section, species: str, props) -> dict[str, float | None]:
    """``species``' double cells ``props`` in the keyed table ``section``
    (``None``: no such column, an empty cell or not a double)."""
    out = {}
    for prop in props:
        cell = section.find_cell(species, prop, None)
        out[prop] = cell.double_value if cell is not None and cell.type_code == 1 else None
    return out


def _named(species: str) -> str:
    """What a model part's error names (D35): ``--player-character``
    and the species, or garret4's own body, which a build wears with no
    ``--player-character`` once a slider isn't 1.0 (Step 2.123)."""
    return f"{PLAYER}'s own body" if species == PLAYER else f"--player-character {species!r}"


def _install_size_early(game, species: str, body: Body, plan: CameraPlan, hung: float,
                        drawn: float = 1.0, swim_eye: bool = False) -> list[str]:
    """The model-size parts a build installs before X10 and X13 (Step
    2.123: the carve allocator lands each shim after the ones before it,
    so this order is the image's; G3's keylord own x2 case pins it): X8
    at ``plan``'s point (its timer mode for a body with no clips drawn
    ``drawn``; with ``swim_eye`` and no X8 in the plan, its swim point
    alone: garret4's own body drawn under x1, Step 2.126, D319), then X9
    (its climb shim, else its zipline hang alone, ``hung`` times
    garret4's grab, :func:`hang_scale`).  Returns what it installed."""
    done = []
    try:
        if plan.x8:   # X8 (Step 2.23c; garret4's fraction of the drawn top, Step 2.107; over a ladder's top, Step 2.116)
            install_eye_shim(game["default.xbe"], plan.aim, plan.margins, over_rows(body), over_timer(body, drawn))
            done.append("X8")
        elif swim_eye and plan.aim is not None:   # X8's swim point alone, his m_head on land (Step 2.126, AZ-576)
            install_eye_shim(game["default.xbe"], plan.aim, plan.margins, land=False)
            done.append("X8 (swim point only)")
        if needs_climb_shim(body):   # X9 (Step 2.63; the zipline hang at the model scale, Step 2.104)
            install_climb_shim(game["default.xbe"], hung)
            done.append("X9")
        elif needs_hang_shim(body, hung):   # X9's zipline hang alone (Step 2.104, AZ-526; at X' != 1, Step 2.118)
            install_hang_shim(game["default.xbe"], hung)
            done.append("X9's zipline hang")
    except ValueError as exc:
        raise ValueError(f"{_named(species)}: {exc}") from None
    return done


def _install_size_late(game, species: str, body: Body, plan: CameraPlan, hung: float, drawn: float,
                       model_scale: float, far: float, hold: HoldPlan | None = None,
                       search: bool = False) -> list[str]:
    """The model-size parts a build installs after X13-X18, in this
    order (:func:`_install_size_early`): X19 and X20 from ``plan``, X21
    out to ``far`` m when that passes 3 m (with ``search``, X37's, at
    least 3 m), X22 off the zipline (``hung``,
    :func:`hang_scale`, :func:`hang_eased`) and X28 after it where
    ``hold`` is needed (:func:`hold_plan`), and X48 where its crossfades
    dip, X23 and X26 over a ladder's top for a body drawn
    ``drawn`` (``model_scale`` times its size's), X27 and X29 for a tiny
    one, X25's rig.  Returns what it installed."""
    done = []
    try:
        # X19 (Step 2.104, AZ-520): X8's point, or the body's own m_head where it rests (Balthazar's)
        if plan.lift >= EYE_LIFT_MIN:
            install_eye_sweep_shim(game["default.xbe"], plan.lift, plan.rig)   # B2 with X25 (Step 2.116d)
            done.append("X19")
        if plan.x20:   # X20 (Step 2.105, AZ-520): the ride's point no lower than the centre
            install_eye_hang_shim(game["default.xbe"])
            done.append("X20")
        if far > SEARCH_RADIUS or search:   # X21 (Step 2.105, AZ-523): the combo on a stunned target out to ``far``
            install_search_shim(game["default.xbe"], max(far, SEARCH_RADIUS))
            done.append("X21")
        # X22 (Step 2.105, AZ-529): off the zipline, the drawn body eases to its stance (x1 too, Step 2.118)
        if hang_eased(body, hung):
            install_hang_ease_shim(game["default.xbe"], hung)
            done.append("X22")
            if hold is not None and hold.needed:   # X28 (Step 2.118c): the drawn hang held over the floors
                install_hold_shim(game["default.xbe"], hold)
                done.append("X28")
            if hold is not None and hold.fade_ray > 0.0:   # X48 (Step 2.189b): the let-go's and landings'
                install_fade_shim(game["default.xbe"], hold)   # crossfades drawn over the floor
                done.append("X48")
        # a baked body drawn at D other than 1, x1 too (Step 2.118, AZ-536, D291), and a body with no clips,
        # whose root rides garret4's m_feet / D (Step 2.127, AZ-562): X23's grab term alone, no X26
        if needs_hang_shim(body, drawn):
            # X23 (Step 2.106, AZ-529): over a ladder's top, the drawn feet onto the floor; X26 (Step 2.116) after;
            # a hoist's end too (Step 2.127, AZ-572)
            install_over_top_shim(game["default.xbe"], timers=not body.clips)
            done.append("X23")
            if body.clips:   # with the climb-over's glide held (Step 2.175b, AZ-529 (c))
                install_stance_term_shim(game["default.xbe"], stance_glide_end(game["characters.xbr"], body))
                done.append("X26")
        if plan.near:   # X27 (Step 2.116, AZ-541): a tiny body drawn with the eye near its centre; X29 (Step 2.116b)
            install_near_draw_shim(game["default.xbe"])
            install_water_push_shim(game["default.xbe"])
            done += ["X27", "X29"]
        if plan.rig:   # X25 (Step 2.107, D280): the level camera's rig at the drawn body's size
            install_camera_rig(game["default.xbe"], plan.s)
            done.append("X25")
    except ValueError as exc:
        raise ValueError(f"{_named(species)}: {exc}") from None
    return done


def sized_roll(game, characters: bytes, body: Body, model_scale: float) -> bool:
    """E (Step 2.133, AZ-608): garret4's roll drawn about his centre at
    ``model_scale``, a copy (:data:`SIZED_ROLL`) added to his body in
    ``game``'s staged files (``characters`` and ``body`` his, before it),
    which his roll column then plays; whether it added one."""
    his = named_clip(characters, PLAYER, G4_ROLL)
    rolled = centred(his, model_scale, body.markers.index(ROOT_NODE),
                     {k: b.t for k, b in enumerate(Rig.read(characters, PLAYER).bones) if b.parent < 0})
    if rolled is his:
        return False
    grown, index = add_clips(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), PLAYER, {SIZED_ROLL: rolled})
    game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
    return True


def refuse_garret4_attacks(attack_balance: bool | None, attack_ground: bool | None) -> None:
    """Raise :class:`ValueError` when the attack balance or the
    reach-to-ground is asked on for garret4's own body (Step 2.123, D35):
    his attacks are the ones the balance weighs against and his boxes
    the ones X13 would lower, so neither has anything to do; off and
    unset (``None``) are accepted."""
    for flag, on, why in (
            ("--player-attack-balance", attack_balance, "garret4 plays his own attacks, the ones the balance weighs "
                                                         "a swapped body's against"),
            ("--player-attack-ground", attack_ground, "garret4's hit boxes are his own, and it lowers only a "
                                                       "swapped body's")):
        if on:
            raise ValueError(f"{flag} on: {why}; pass off, or leave it unset")


@dataclass
class _Recipe:
    """A recipe on garret4's own body as :func:`_apply_garret4` builds it
    (Step 2.206, D813): the ``variant``, the moveset it plays (``worn``:
    its own, or :func:`~azurik_mod.patches._player_variants.unarmed`
    under another weapon), its WAVs and drop-ins (``drop``,
    :func:`~azurik_mod.patches._player_variants.variant_sounds`) and the
    :func:`apply_player_model` options its layers read."""

    variant: object
    worn: object
    drop: dict
    jiggle_strength: float = 1.0
    jiggle_stiffness: float = 1.0
    springs_out: dict | None = None
    plans: list | None = None
    ram: int | None = None


def _layered(variant, worn, drop: dict) -> bool:
    """Whether a recipe on garret4's own body (Step 2.206, D813) asks his
    own build for more than its options (scale, attack numbers, weapon)
    and its colours: a look, a move, a slot or a sound of its own."""
    return bool(variant.mesh is not None or variant.jiggle is not None or variant.textures or variant.arms
                or variant.arm_clips or variant.poses or variant.lods is not None or variant.shadow is not None
                or variant.idles or variant.slots or variant.victory_cancel is not None or variant.voice != "own"
                or variant.wavs or drop or worn.markers or worn.clips or worn.columns or worn.carry or worn.held
                or worn.rotate or worn.fx_edits or worn.effects or worn.through_walls or worn.sfx)


def _his_look(game, variant, who: str) -> tuple:
    """A recipe's W24 mesh, W29 jiggle bones and W30 textures made on
    garret4's own body in ``game``'s staged characters.xbr, in place
    (Step 2.206; only he wears it), first, so every measure of his build
    reads them (:func:`_variant_body`); its mesh plan, rig and W30's log
    lines.  :class:`ValueError` names the step that fails (D35)."""
    try:
        made, reshaped, rigged, painted = _variant_body(bytes(game["characters.xbr"]), game.stored("characters.xbr"),
                                                        PLAYER, variant)
    except ValueError as exc:
        sized = ", ".join(f"{s.title} {s.value:g}" for s in variant.shapes if s.value != 1.0)
        raise ValueError(f"{who}" + (f" at {sized}" if sized else "") + f": {exc}") from None
    game["characters.xbr"] = bytearray(made)
    if variant.lods is not None:   # W39's cuts (none of W36's)
        _lods_ahead(made, PLAYER, variant.lods)
    else:
        engine = XbrDocument.from_bytes(game.stored("config.xbr")).keyed_section("critters_engine")
        _shadow_ahead(made, engine, PLAYER, PLAYER, variant.shadow)
    return reshaped, rigged, painted


def _his_moves(game, characters: bytes, body: Body, variant, worn, who: str, first: int) -> tuple:
    """A recipe's W22 on garret4's own body (Step 2.206): its markers
    grown and its clips under ``characters/garret4/v/``, its fx clone
    (:func:`~azurik_mod.patches._player_variants.grow`); X11's fills from
    its ``slots`` and ``idles`` (its base loops, :data:`CALM_SEAM`), the
    gait and move checks as any body's; and W28's arms and poses on every
    clip he plays but its own ``v/`` ones (``characters`` the staged file
    before W22, ``first`` its TOC count).  Returns the file, his body
    read from it, the fills, the victories and how many clips W28 turned."""
    from azurkit.tools.characters import _player_variants as variants

    dressed = characters
    if worn.markers or worn.clips or worn.fx_edits:
        try:
            grown, index = variants.grow(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body, worn,
                                         game.stored("default.xbe"), game.stored("fx.xbr"))
        except ValueError as exc:
            raise ValueError(f"{who}: {exc}") from None
        game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
        characters, body = grown, variants.reread(grown, body)
    slotted = recipe_fills(worn.slot_clips())
    fills = {k: v for k, v in slotted.items() if k not in VICTORIES}
    victory = {k: v for k, v in slotted.items() if k in VICTORIES}
    if worn.idles:   # X11's idle slots (Step 2.168, D553): its base loops, its fidgets play once (X45)
        idles = worn.idle_clips()
        seam = base_seam(characters, PLAYER, idles["idle"])
        if seam > CALM_SEAM:
            raise ValueError(f"{who}: idles.idle: {idles['idle']} doesn't end where it starts (seam {seam:.3f} > "
                             f"{CALM_SEAM:g} model units), so it can't loop as the base")
        fills |= idle_fills(idles)
    named = f"{variant.name!r} (a variant of {PLAYER})"   # as the swap's checks name it
    gait_checks(characters, body, worn, named)
    move_checks(characters, body, worn, named)
    styled = 0
    if variant.arms or variant.arm_clips or variant.poses:   # W28 (Step 2.143, D428): his clips' arms and poses
        try:
            grown, styled, _ = variants.restyled(dressed, bytes(game["characters.xbr"]), first, PLAYER, variant)
        except ValueError as exc:
            raise ValueError(f"{who}: {exc}") from None
        game["characters.xbr"] = bytearray(grown)
        characters = grown
    return characters, body, fills, victory, styled


def _his_cells(game, doc, anims, characters: bytes, body: Body, worn, lo, columns: list[str], picks: list[str],
               fills: dict, model_scale: float, shot, who: str) -> tuple:
    """A recipe's config.xbr cells on garret4's own build (Step 2.206):
    W22's hitsThroughWalls, W37's planted chain, W7's stride where its
    ``slots`` name a gait (by the clip's planted feet; his own slots keep
    his cells) and X42's projectile species rows (``shot``, its plan).
    Returns the stride, W37's chain, the throw's plan and its rows."""
    stride, looped, toss, rows = {}, None, None, []
    if worn.through_walls:   # W22 (Step 2.140, D385): his hits skip the wall test
        set_keyed_double(doc.keyed_section("critters_critter_data"), PLAYER, "hitsThroughWalls", 1.0)
    loop = worn.loop()
    if loop is not None:   # W37 (Step 2.180, D701)
        looped = planted_chain(anims, doc.keyed_section("attacks_transitions"), tuple(loop["plant"]),
                               float(loop["turns"]), float(loop["hold"]))
    named = frozenset(recipe_fills(worn.slot_clips()))
    gait = [prop for prop, slot in zip(_STRIDE, STRIDE_SLOTS) if slot in named]
    if gait:   # W7 (Step 2.171): its gait by its planted feet
        data = doc.keyed_section("critters_critter_data")
        plays = {i: c for i, name in enumerate(BASE_CLIPS) for c in body.clips if c.casefold() == name} | {
            i: c for i, (c, _) in fills.items()}
        his = _doubles(data, PLAYER, _STRIDE)
        stride = {p: v for p, v in stride_cells(characters, body, plays, his, his, named).items() if p in gait}
        for prop, value in stride.items():
            set_keyed_double(data, PLAYER, prop, value)
    if shot is not None:   # Step 2.167b (D538's E2): its projectile, released at each column clip's first hit
        try:
            timing = shot_timing(characters, body, body, anims, columns, picks, {}, model_scale, shot)
            toss = throws.template_plan(shot, game.stored("characters.xbr"), columns, timing, doc, model_scale,
                                        throw_bone(characters, body, lo, picks))
        except ValueError as exc:
            raise ValueError(f"{who}: {exc}") from None
        v = shot.values
        rows = throws.write_species(doc, toss.scale, min(float(v["radius"]), float(v["size"]) / 2))
    return stride, looped, toss, rows


def _his_recipe(game, recipe: _Recipe, who: str, characters: bytes, body: Body, columns: list[str],
                picks: list[str], anims, fills: dict, victory: dict, model_scale: float, lo, shot, toss, seek: int,
                rigged, dressed: bytes, first: int, doc, attack_reach: float, every: int, x26: bool
                ) -> tuple[list[str], list[str], list]:
    """A recipe's shims and its sounds and springs on garret4's own build
    (Step 2.206, D813), after his own parts and before the hoe's (W31-W33
    come after X41, as the swap's): X11's slots, X45, X46, X10's ring over
    its columns' clips, X33, X39, X49, its shield and beam rows (X38's
    bound keys), X40 (its fx clone), X42 (its projectile, X32 where it
    hits with a type), X14, X15 and W9 (its sounds), W28's springs and
    X41.  Returns its words, its sounds' log lines and what it adds to
    fx.xbr (written last, :func:`_his_tail`)."""
    from azurkit.tools.characters import _player_variants as variants

    variant, worn, xbe = recipe.variant, recipe.worn, game["default.xbe"]
    words: list[str] = []
    rotate = rotated = None
    search_at = lambda: trampoline_symbol_va(xbe, SEARCH_HOOK, SEARCH_RADIUS_SYMBOL, CHECKOUT,   # noqa: E731
                                             shim_source=SEARCH_SHIM.source_path())
    carried, held = variants.carried(worn, columns), variants.held(worn, columns)
    blasts, impact = variants.blasts(worn, columns)
    fidgets = fidget_mask(variant.idle_clips())
    try:
        if fills or victory:   # X11 (Steps 2.168, 2.171): its idles, gait, jumps and victories in his slots
            install_slots_shim(xbe, fills | victory)
        if fidgets:   # X45 (Step 2.168, D553)
            install_idle_pick(xbe, fidgets, variant.idle_wait)
        if variant.victory_cancel is not None:   # X46 (Step 2.181, D702)
            install_victory_cancel(xbe, variant.victory_cancel)
        rotate = rotation(columns, picks, body) if worn.rotate else None
        if rotate:   # X10 (Step 2.64): each swing the next of the clips that can hit (Step 2.69)
            rotate = hitting_ring(characters, body, picks, model_scale, rotate)
            rotated = install_rotate_shim(xbe, *rotate)
            words.append(f"each swing the next of {len(rotate[0])} attack clips (X10)")
        if carried or held:   # X33 (Steps 2.132, 2.153)
            install_attack_carry_shim(xbe, carried, held)
            words += ([f"{carried.bit_count()} attacks moving with the stick (X33)"] if carried else []) + (
                [f"{held.bit_count()} attacks chaining while A or B is held (X33's held mask)"] if held else [])
        if blasts:   # X39 (Step 2.153, D451)
            install_air_blast_shim(xbe, blasts, impact)
            words.append(f"its air blast played where it lands, at {impact:g} s (X39)")
        if seek:   # X49 (Step 2.194b, D762)
            install_seek_shim(xbe, seek, search_at())
            words.append(f"its {', '.join(c for i, c in enumerate(columns) if seek >> i & 1)} turning to their target "
                         "at the attack's start (X49)")
    except ValueError as exc:
        raise ValueError(f"{who}: {exc}") from None
    shields = bound_rows(worn, lo, variant.name) if worn.effects else []
    if shields:   # Step 2.167c (D538's E3): each its graph of its own, on X38's bound keys
        new, bound = [], []
        base = len(parse_toc(game["characters.xbr"]))
        point = action_point(characters, body, picks)
        for k, e in enumerate(shields):
            t = e.template
            unknown = [c for c in e.columns if c not in columns]
            if unknown:
                raise ValueError(f"{who}: its {t.name} row: columns: {unknown[0]!r} is no attacks_anims column")
            values = dict(e.values)
            for name, param in t.params.items():   # range "auto": the columns' boxes' reach ahead (m)
                if values[name] == "auto":
                    got = melee_reach(characters, body, columns, picks, model_scale, every, GARRET4_FORWARD,
                                      reach=attack_reach, only=e.columns, melee=False, ahead=True)
                    values[name] = got if got else param["default"]
            anchor, at, grow = bound_place(characters, body, body, point, anims, columns, picks, {}, model_scale, e)
            try:
                made, b, _ = fx_ring.bound_graph(bytes(game["characters.xbr"]), game.stored("default.xbe"),
                                                 game.stored("fx.xbr"), e, fx_ring.bound_key(PLAYER, t.name, k),
                                                 base + len(new), marker=anchor, at=at, scale=grow, values=values)
            except ValueError as exc:
                raise ValueError(f"{who}: {exc}") from None
            new += made
            bound.append(replace(b, columns=tuple(columns.index(c) for c in e.columns)))
            words.append(f"its {t.name} row (template {t.name}@{fx_templates.template_sha(t.name)}): a {t.group} on "
                         f"{', '.join(e.columns)}, {b.key} ({b.records} records), its holder "
                         + (f"bound to {anchor}" if anchor else f"at ({', '.join(f'{c:.3f}' for c in at)})")
                         + " (X38's bound key)")
        game["characters.xbr"] = bytearray(append_resources(bytes(game["characters.xbr"]), new))
        game["index.xbr"] = bytearray(add_index_records(
            bytes(game["index.xbr"]), [IndexRecord(r.name, "characters.xbr", r.tag) for r in new if r.name]))
        played = {i: anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns) if col != ROLL}
        try:
            ringed = fx_ring.ring_plan(bytes(game["characters.xbr"]), game.stored("default.xbe"), body, played,
                                       [played[h] for h in rotate[0]] if rotated else None, {}, bound=tuple(bound),
                                       turns=rotate[1] if rotated else 0, own=False)
            install_fx_ring_shim(xbe, ringed, rotated or 0, 0)
        except ValueError as exc:
            raise ValueError(f"{who}: {exc}") from None
    if worn.fx_edits:   # X40 (Step 2.157, D446): his clone of his fx_default, which only he wears anyway
        try:
            install_fx_default_shim(xbe, bytes(game["characters.xbr"]), bytes(game["index.xbr"]), PLAYER)
        except ValueError as exc:
            raise ValueError(f"{who}: {exc}") from None
        words.append(f"his clone of characters/{PLAYER}/fx/fx_default, {fx_edit.clone_key(PLAYER)}, retuned at "
                     f"{len(worn.fx)} records"
                     + "".join(f", {g.get('template') or g['from']['key']} grafted under record {g.get('parent')}"
                               for g in worn.fx_grafts) + " (X40)")
    hit_fx = shot is not None and shot.template.hit is not None
    if toss is not None:   # W30 and X42 (Step 2.167b): the projectile as data, thrown from his hand
        try:
            grown, index, info = throws.write_template(bytes(game["characters.xbr"]), bytes(game["index.xbr"]),
                                                       game.stored("default.xbe"), game.stored("fx.xbr"), shot,
                                                       toss.scale)
            game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
            install_throw_shim(xbe, toss.table(), search_at())
            if hit_fx:   # X32 (Step 2.180, D700): its hits' small flash
                install_hit_fx_shim(xbe)
        except ValueError as exc:
            raise ValueError(f"{who}: its throw: {exc}") from None
        t = shot.template
        words.append(f"its {t.name} row (template {t.name}@{fx_templates.template_sha(t.name)}): "
                      + ", ".join(f"{columns[c.column]} throws it out at tick {c.release} of {c.ticks}"
                                  for c in toss.shots)
                      + f" (W30: {throws.SPECIES} at x{toss.scale:.3f}, {info['bytes']} B; X42"
                      + (", X32's flash on its hits" if hit_fx else "") + ")")
    drop = {leaf: d for leaf, d in recipe.drop.items() if d.role in worn.sfx or d.role in variants.DROP_ROLES}
    voice: list[str] = []
    waves: list = []
    if variant.voice != "own" or worn.sfx or drop:   # his sounds (Step 2.141; D328, D384, D386): his are Garret's,
        made = variants.waves(worn, drop)   # so X14 binds its own from its dir and keeps his elsewhere
        roles = variant_roles(PLAYER, variants.sound_dir(variant), columns,
                              {col: name for name, p in worn.sfx.items() for col in p["columns"]},
                              variant.voice == "silent", frozenset(d.role for d in drop.values()) - set(worn.sfx))
        try:
            emptied = write_sound_cells(doc, roles)
            if roles.binds:
                install_sounds_shim(xbe, roles)
            if roles.xbe:
                install_xbe_sounds(xbe, roles)
        except ValueError as exc:   # XbrStructuralError too
            raise ValueError(f"{who}: {exc}") from None
        waves = [NewResource(f"{variants.sound_dir(variant)}/{leaf}", "wave", wave_entry(samples))
                 for leaf, samples in made.items()]
        takes = {name: (sum(variants.take_name(name, k) in made for k in range(variants.TAKES)), len(p["columns"]))
                 for name, p in sorted(worn.sfx.items())}
        voice = describe_variant(roles, emptied, columns, takes, len(waves), sum(len(e.payload) for e in waves), [
            f"{d.origin} {d.path.name}: {leaf} (sha256 {d.sha256[:12]}), {len(d.samples) / SOUND_RATE:.3f} s from "
            f"{d.info.rate} Hz, {d.info.channels} channel{'s' * (d.info.channels > 1)}, {d.info.bits}-bit"
            + (f"; past the game's longest inline wave ({LONGEST_WAVE} s), unseen in game"
               if len(d.samples) / SOUND_RATE > LONGEST_WAVE else "") for leaf, d in sorted(drop.items())])
    flash = hit_flash(game.stored("fx.xbr"), game.stored("default.xbe")) if hit_fx and toss is not None else []
    if rigged is not None:   # W28's springs (Step 2.143, AZ-648): last, at the rates his written cells play each clip
        built = bytes(game["characters.xbr"])   # each column's clip as W3 wrote it (his sized roll, his lunges)
        rates = playback_rates(built, doc, body, fills | victory, [anims.find_cell(col, "Anim", i).string_value
                                                                    for i, col in enumerate(columns)],
                               model_scale, False)
        try:
            grown, _, peaks = variants.restyled(dressed, built, first, PLAYER, variant, rigged, rates, model_scale,
                                                arms=False)
        except ValueError as exc:
            raise ValueError(f"{who}: {exc}") from None
        game["characters.xbr"] = bytearray(grown)
        sprung: list[jiggle_rt.Row] = []
        if jiggle_rt.spring_bones(variant.jiggle):   # X41 (Step 2.156; D444, D445): last in the XBE
            built = bytes(game["characters.xbr"])
            binds = inverse_binds(built, PLAYER)
            bones_ = Rig.read(built, PLAYER).bones
            parents = [b.parent for b in bones_]
            try:
                placed = (*rigged.bones, *jiggle_rt.spring_places([b.name for b in bones_], parents, binds,
                                                                   variant.jiggle.springs))
                sprung = jiggle_rt.rows(placed, jiggle_rt.spring_bones(variant.jiggle), binds,
                                        recipe.jiggle_stiffness, parents)
                if recipe.springs_out is not None:
                    recipe.springs_out.update(
                        rows=sprung, placed=placed, parents=parents, binds=binds, rates=rates, body=PLAYER,
                        characters=built, drawn=model_scale, strength=recipe.jiggle_strength,
                        stiffness=recipe.jiggle_stiffness,
                        slots={k: c for k, n in enumerate(BASE_CLIPS) for c in body.clips if c.casefold() == n}
                        | {k: c for k, (c, _) in (fills | victory).items()},
                        cells=_doubles(doc.keyed_section("critters_critter_data"), PLAYER,
                                       (*_STRIDE, WALK_SPEED, RUN_SPEED)))
                if recipe.jiggle_strength != 0.0:
                    stance = (tuple(trampoline_symbol_va(xbe, STANCE_HOOK, f"_player_model_stance_{w}", CHECKOUT,
                                                         shim_source=STANCE_SHIM.source_path())
                                    for w in ("held", "edge")) if x26 else (0, 0))
                    # X41 steps a body of the table's bone count: his hoe's W31 carriers come after (AZ-783)
                    carried = len(lo.prop.carriers) if lo is not None and lo.picked else 0
                    install_jiggle_shim(xbe, jiggle_rt.table(sprung, len(bones_) + carried, recipe.jiggle_stiffness,
                                                             model_scale), recipe.jiggle_strength, stance)
            except ValueError as exc:
                raise ValueError(f"{who}: {exc}") from None
        words.append(_jiggle_line(rigged, peaks, variant, sprung, recipe.jiggle_strength, recipe.jiggle_stiffness))
    return words, voice, [*flash, *waves]


def _his_tail(game, recipe: _Recipe, who: str, engine, added: list) -> tuple[list[str], list[str]]:
    """The last of a recipe on garret4's own build (Step 2.206), after the
    hoe's parts: what it adds to fx.xbr (X32's flash, its sounds), W39's
    LODs and W36's shadow LOD (for a recipe with a mesh or ``lods``), W38
    in place (his rows recoloured, no copy and no X47: only he wears his
    body, Step 2.170c) and the load budget.  Returns W38's words and the
    LOD and budget lines."""
    from azurkit.tools.characters.model_inspect import DEFAULT_RAM
    from azurkit.tools.characters import _player_variants as variants

    variant = recipe.variant
    if added:
        try:
            game["fx.xbr"] = bytearray(append_resources(bytes(game["fx.xbr"]), added))
            game["index.xbr"] = bytearray(add_index_records(
                bytes(game["index.xbr"]), [IndexRecord(e.name, "fx.xbr", e.tag) for e in added if e.name]))
        except ValueError as exc:
            raise ValueError(f"{who}: its sounds: {exc}") from None
    laid, lods_bytes, shadowed, shadow_bytes = [], 0, [], 0
    if variant.lods is not None or variant.mesh is not None:   # W39 (Step 2.166d) after W33, before W36
        try:
            laid, lods_bytes = write_lods(game, engine, PLAYER, variant.lods,
                                          game.stored("characters.xbr") if variant.mesh is not None else None)
        except ValueError as exc:
            raise ValueError(f"{who}: W39: {exc}") from None
    if variant.mesh is not None or variant.shadow is not None:   # W36 (Step 2.166c)
        try:
            shadowed, shadow_bytes = write_shadow_lod(game, engine, PLAYER, variant.shadow)
        except ValueError as exc:
            raise ValueError(f"{who}: W36: {exc}") from None
    coloured = []
    if variant.colours:   # W38 in place (Step 2.170c, D748): after every other write of his body
        try:
            grown, _, coloured = write_colours(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), PLAYER,
                                               located(variant.colours, variants.colour_folder(variant)),
                                               in_place=True)
        except ValueError as exc:
            raise ValueError(f"{who}: {exc}") from None
        game["characters.xbr"] = bytearray(grown)
    budget = _load_budget(game, PLAYER, variant.name, bool(added), DEFAULT_RAM if recipe.ram is None else recipe.ram,
                          shadow_bytes, lods_bytes)
    words = ([f"his colours in his own body's rows, in place (W38, no copy: only he wears it): "
              f"{'; '.join(coloured) or 'none'}"] if variant.colours else [])
    return words, [*laid, *shadowed, *budget]


def _apply_garret4(game, model_scale: float, attack_reach: float, attack_damage: float, attack_speed: float,
                   attack_balance: bool | None, attack_ground: bool | None, logic: AttackLogic | None,
                   lo: Loadout | None = None, mode: str = DEFAULT_MODE, recipe: "_Recipe | None" = None,
                   chain: str = DEFAULT_CHAIN) -> list[str]:
    """:func:`apply_player_model` for garret4's own body (Step 2.123,
    D302, D312): drawn ``model_scale`` times his size, W2's scale and his
    bound grown with it, and the size parts his body needs (X9's zipline
    hang, X19, X20, X22, X28 where his hang reaches deeper than x1's
    past :data:`G4_SPAN` (x1.098 up, Step 2.127), X23, X26, X27, X29, X25;
    :func:`_install_size_early`, :func:`_install_size_late`) only off x1
    exactly (his hang pose's top gives :func:`hang_scale` 0.99999996 at
    x1); drawn larger, his staff checked against the walls at x1 (X30,
    D317); drawn smaller, X8's swim point with his own ``m_head`` on land
    (D319); his hit boxes ``attack_reach`` times as far (X13, no bump),
    and drawn at a size other than 1 filled to his feet and the floor
    (X13's fill, Step 2.132, D347: "including for big models"); W14 on his
    own table: every attack's Damage multiplier but the
    roll's ``attack_damage`` times his own (X18 where a light hit reaches
    1.0) and its Rate ``attack_speed`` times, his basics' chain held
    inside the stun (:func:`speed_chain`); X21's combo search out to 3 m
    x size x reach where that passes 3 m; off x1 his roll column plays
    :data:`SIZED_ROLL`, his roll drawn about his centre at his size
    (Step 2.133, AZ-608).  Nothing of the swap's: his body
    has every clip, marker and box it would add, so every mode, size, clip
    and sound option builds the same bytes; the balance and
    reach-to-ground asked on are refused (:func:`refuse_garret4_attacks`).
    ``logic`` receives his reach, damage and speed at every value, the
    vanilla ones too.  ``lo`` the weapon he wears (:func:`loadout`): with
    a prop on his staff chain (Step 2.161d: the hoe, :data:`ON_CHAIN`)
    his staff is cut from his mesh (W33, :func:`cut_staff`), the prop's
    mesh where W26's carrier would ride his ``m_stafftop`` (W32,
    :func:`copy_prop`), X3 gives every column his own box and
    window grown to its tip (:func:`held_window`, as a farmer's),
    his staff's fx, power heads and trails bound to its two carriers at
    its ends under his ``m_stafftop`` (Step 2.161g, D618: W31, W6 without
    the shrink; W4 can't hide them on him, his bind writing their scale
    every frame), the mesh skinned to the tip one, which his clips that
    would put the prop under the floor key turned up about his grip
    (W41, Step 2.207, AZ-784: :func:`chain_lifted`), and the balance (his own attacks: nothing to weigh) and the
    reach-to-ground (X13's fill under X3's rows) are taken, unset off.
    ``recipe`` (Step 2.206, D813): a recipe on his own body, its layers
    made on this build (:class:`_Recipe`): its look first (W24, W29, W30:
    every measure reads it), its clips and markers (W22), arms and poses
    (W28), its columns playing their clips at his Rates (a Blender clip's
    own, Step 2.158) and his chain, its slots, idles and victories (X11,
    X45, X46, W7 by its planted feet), X10, X33, X39, X49, W37, its
    effects rows (X42, X38's bound keys), its fx clone (X40), its sounds
    (X14, X15, W9), its springs (W28, X41), LODs (W39, W36) and its
    hitsThroughWalls (W22); the rest his own build's (no W5, W14 balance,
    W19, X3 or X36 on his columns).  ``chain`` "any" (D1045) lifts his
    combo's gate (:func:`lift_chain_gates`)."""
    armed = lo is not None and lo.picked
    if not armed:
        refuse_garret4_attacks(attack_balance, attack_ground)
    from azurkit.tools.characters import _player_variants as variants
    variant, worn = (recipe.variant, recipe.worn) if recipe is not None else (None, None)
    who = f"--player-character {variant.name!r} (a variant of {PLAYER})" if variant is not None else _named(PLAYER)
    reshaped = rigged = None
    painted: list[str] = []
    if variant is not None and (variant.mesh is not None or variant.jiggle is not None or variant.textures):
        reshaped, rigged, painted = _his_look(game, variant, who)   # W24, W29, W30: first, every measure reads them
        if recipe.plans is not None and reshaped is not None:
            recipe.plans.append(reshaped)
    characters = game.stored("characters.xbr") if variant is None else bytes(game["characters.xbr"])
    body = read_body(characters, PLAYER)
    dressed, first = characters, len(parse_toc(characters))   # W28's start: the clips this build adds after
    fills: dict[int, tuple[str, float]] = {}
    victory: dict[int, tuple[str, float]] = {}
    styled = 0
    if worn is not None:   # W22 (his markers, clips, fx clone), his idles and slots (X11), W28's arms and poses
        characters, body, fills, victory, styled = _his_moves(game, characters, body, variant, worn, who, first)
    vanilla = XbrDocument.from_bytes(game.stored("config.xbr")).keyed_section("attacks_anims")
    columns = vanilla.col_names()
    clips = [vanilla.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]
    picks = [worn.clip_of(col) or clip for col, clip in zip(columns, clips)] if worn is not None else clips
    recipe_picks = {i: p for i, p in enumerate(picks) if worn is not None and worn.clip_of(columns[i])}
    given = {i: r for i, col in enumerate(columns)   # a recipe's Blender clip at the Rate it gives (Step 2.158)
             if worn is not None and (r := variants.clip_rate(worn, col)) is not None}
    rates = [given.get(i, vanilla.find_cell(col, "Rate", i).double_value) for i, col in enumerate(columns)]
    shape = camera_shape(characters, body)
    every = (1 << len(columns)) - 1 if armed else 0   # Step 2.161d: X3's rows grown to the hoe's tip
    if logic is not None:   # his own Anims, his own boxes drawn at the size (Step 2.73, AZ-559)
        logic.reach = melee_reach(characters, body, columns, picks, model_scale, every, GARRET4_FORWARD,
                                  exact=clips if armed else None, reach=attack_reach, model_scale=model_scale,
                                  ahead=True, held=lo if armed else None, only=IDLE_SWINGS,   # AZ-566
                                  rates=rates)   # AZ-766: from the body
        logic.damage, logic.speed = attack_damage, attack_speed
        logic.size = movement_size(SizeShape(shape, None, 1.0), model_scale)   # Step 2.133
    colour, why = mode_status(PLAYER, model_scale=model_scale)
    if (model_scale, attack_reach, attack_damage, attack_speed) == (1.0, 1.0, 1.0, 1.0) and not armed and not (
            variant is not None and _layered(variant, worn, recipe.drop)) and chain != "any":
        return [f"  Player model: {PLAYER}, the vanilla player ({colour}); nothing written"]
    doc = _load_doc_for_edit(game, "config.xbr")
    engine, anims = doc.keyed_section("critters_engine"), doc.keyed_section("attacks_anims")
    own = _species(engine)[PLAYER]["boundRadius"] or 0.0
    bound = own * model_scale
    sized = model_scale != 1.0
    chained: list[str] = []
    copied, lunges = False, {}
    stride: dict[str, float] = {}
    looped = toss = None
    toss_rows: list = []
    seek = variants.seeking(worn, columns) if worn is not None else 0
    shot = projectile_row(worn, lo, variant.name) if worn is not None and worn.effects else None
    search = bool(seek) or shot is not None   # X49 and X42 read X21's radius
    try:
        if sized:   # W2: his scale, and his bound grown with it, never under his own
            set_keyed_double(engine, PLAYER, "scale", model_scale, fill_empty=True)
            if bound > own:
                set_keyed_double(engine, PLAYER, "boundRadius", bound)
            if sized_roll(game, characters, body, model_scale):   # E (Step 2.133, AZ-608)
                set_keyed_string(anims, ROLL, "Anim", SIZED_ROLL, col=columns.index(ROLL))
                copied = True
            lunges = attack_copies(characters, body, [c for col, c in zip(columns, picks) if col != ROLL], "own",
                                   model_scale)   # and his lunges (AZ-623; the roll is p/roll's)
            if lunges:
                grown, index = add_clips(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), PLAYER,
                                         dict(lunges.values()))
                game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
        if lunges or recipe_picks:   # W3: his lunges drawn about his centre, a recipe's columns (Step 2.206)
            names = {clip: name for clip, (name, _) in lunges.items()}
            played = [SIZED_ROLL if copied and col == ROLL else names.get(c, c) for col, c in zip(columns, picks)]
            write_anims(anims, place_anims(columns, anim_strings(anims), played))
        for i, rate in given.items():   # a recipe's Blender clip at the Rate it gives (Step 2.158)
            set_keyed_double(anims, columns[i], "Rate", rate, col=i)
        for i, col in enumerate(columns):   # W14 on his own table, every attack but the roll
            if col == ROLL:
                continue
            if attack_damage != 1.0:
                cell = vanilla.find_cell(col, MULTIPLIER, i)
                base = cell.double_value if cell is not None and cell.type_code == 1 else 1.0
                set_keyed_double(anims, col, MULTIPLIER, base * attack_damage, col=i, fill_empty=True)
            if attack_speed != 1.0:
                set_keyed_double(anims, col, "Rate", rates[i] * attack_speed, col=i)
                end1 = (speed_chain(vanilla, i, body.length(picks[i]), damage_windows(characters, PLAYER, picks[i]),
                                    attack_speed, follow_hit(vanilla, i, lambda j: (
                                        body.length(picks[j]), damage_windows(characters, PLAYER, picks[j]))))
                        if col in CHAINED and i not in given else None)
                if end1 is not None:
                    set_keyed_double(anims, col, "Move end1", end1, col=i)
                    chained.append(col)
        if worn is not None:   # the recipe's cells (Step 2.206): W22's hitsThroughWalls, W37, W7, X42's species
            stride, looped, toss, toss_rows = _his_cells(game, doc, anims, characters, body, worn, lo, columns,
                                                         picks, fills, model_scale, shot, who)
        if chain == "any":   # D1045: his combo on any press too
            lift_chain_gates(doc)
    except XbrStructuralError as exc:
        raise ValueError(f"{_named(PLAYER)}: {exc}") from None
    light = light_columns(vanilla)
    heavy = attack_damage != 1.0 and any(light >> i & 1 and (c := anims.find_cell(col, MULTIPLIER, i)) is not None
                                         and c.type_code == 1 and c.double_value >= LIGHT
                                         for i, col in enumerate(columns))
    far = SEARCH_RADIUS * model_scale * attack_reach
    filled = fill_mask(columns) if sized or armed and attack_ground else 0
    if sized:
        hung = hang_scale(model_scale, model_scale, hang_top(characters, body, {}))
        plan = camera_plan(shape, None, model_scale, model_scale, hung * G4_HANG_GRAB)
        parts = _install_size_early(game, PLAYER, body, plan, hung, swim_eye=model_scale < 1.0)
    try:
        if armed:   # X3 (Step 2.161d): his own box and window in every column, grown to the hoe's tip (W26's rows)
            install_damage_marker(game["default.xbe"], PLAYER, columns=every, boxes=garret4_boxes(
                characters, clips, lambda clip: held_window(characters, clip, model_scale, lo)))
        if model_scale > 1.0:   # X30 (Step 2.126, D317): his staff checked against the walls at x1
            install_staff_at_x1(game["default.xbe"])
        if attack_reach != 1.0 or filled:   # X13: his boxes that many times as far, filled when sized or asked
            install_attack_box_shim(game["default.xbe"], attack_reach, filled)
        if heavy:   # X18: a light hit written at 1.0 or more still stuns
            install_light_hit_shim(game["default.xbe"], light)
        if shortens_hit_delay(attack_speed):   # X31 (Step 2.126, D318): his hits' no-hit window / the speed
            install_hit_delay_shim(game["default.xbe"], attack_speed)
        if not sized and (far > SEARCH_RADIUS or search):   # X21, as _install_size_late places it
            install_search_shim(game["default.xbe"], max(far, SEARCH_RADIUS))
    except ValueError as exc:
        raise ValueError(f"{_named(PLAYER)}: {exc}") from None
    attacked = ((["X3"] if armed else []) + (["X30"] if model_scale > 1.0 else [])
                + (["X13"] if attack_reach != 1.0 or filled else [])
                + (["X18"] if heavy else []) + (["X31"] if shortens_hit_delay(attack_speed) else [])
                + (["X21"] if not sized and (far > SEARCH_RADIUS or search) else []))
    if sized:   # X28 as the swap's (Step 2.127, AZ-529): his hang deeper than x1's, from x1.098
        hold = hold_plan(characters, body, {}, model_scale, hung) if hang_eased(body, hung) else None
        parts += attacked + _install_size_late(game, PLAYER, body, plan, hung, model_scale, model_scale, far, hold,
                                               search=search)
    else:
        parts = attacked
    moved = movement_size(SizeShape(shape, None, 1.0), model_scale)
    if moved != 1.0:   # X34 (Step 2.133; D344, D356): his pickup touch at his size, after the size parts
        try:
            install_touch_shim(game["default.xbe"], moved)
        except ValueError as exc:
            raise ValueError(f"{_named(PLAYER)}: {exc}") from None
        parts.append("X34")
        walk = write_walk_speed(game, doc, moved)   # beside it, his walk/run switch at his size (D422)
    said: list[str] = []
    voice: list[str] = []
    added: list = []
    if recipe is not None:   # Step 2.206 (D813): the recipe's shims, sounds and springs, then the hoe's parts
        said, voice, added = _his_recipe(game, recipe, who, characters, body, columns, picks, anims, fills, victory,
                                         model_scale, lo, shot, toss, seek, rigged, dressed, first, doc,
                                         attack_reach, every, "X26" in parts)
    if armed:   # Step 2.161d: W33, his staff cut; W32, the hoe on his m_stafftop; Step 2.161g (D618): W31, its
        # carriers at its ends under his m_stafftop, and W6 his staff's fx there: his powers' heads whole (the Axion's
        # power heads), the plain staff's head hidden with the staff (Step 2.206b, AZ-782)
        try:
            fx = _load_doc_for_edit(game, "fx.xbr")
            grown = add_carriers(bytes(game["characters.xbr"]), body, lo)
            heads, euler = power_shape(game, None, body, lo, None)
            hid = follow_hands(fx, lo.fx_ends, heads, euler, shrink=False)   # laid along the hoe (Step 2.182, D707)
            grown, cut = cut_staff(grown, lo)
            grown, propped = copy_prop(grown, body, lo)
            grown, lifted = chain_lifted(grown, lo)   # W41 (Step 2.207, AZ-784): over the floor in his clips
            grown, faded = faded_lifted(grown, PLAYER, lo)   # and through their crossfades (Step 2.207c, AZ-806)
        except (ValueError, XbrStructuralError) as exc:
            raise ValueError(f"{_named(PLAYER)}: {lo.name}: {exc}") from None
        game["characters.xbr"] = bytearray(grown)
    tail: list[str] = []
    if recipe is not None:   # its fx.xbr sounds, W39, W36, W38 in place and the budget, last (Step 2.206)
        coloured, tail = _his_tail(game, recipe, who, engine, added)
        said += coloured
    words = {"X13": f"X13 (hit boxes x{attack_reach:g}" + (", filled to the feet and the floor)" if filled else ")"),
             "X3": "X3 (his own box and window in every column, grown to the hoe's tip)",
             "X21": f"X21 out to {max(far, SEARCH_RADIUS):.2f} m",
             "X30": "X30 (the staff checked at x1)", "X31": f"X31 (his hits' no-hit window / {attack_speed:g})",
             "X25": f"X25 (rest {rest_distance(plan.s):.2f} m)" if sized and plan.rig else "X25",
             "X34": f"{touch_words(moved)}, {walk_words(walk)}" if moved != 1.0 else ""}
    done = ([f"scale {model_scale:g}" + (f", boundRadius {bound:g}" if bound > own else "")] if sized else []) + (
        [f"the roll drawn about his centre ({SIZED_ROLL})"] if copied else []) + (
        [f"his {', '.join(sorted(lunges))} drawn about his centre ({', '.join(n for n, _ in lunges.values())})"]
        if sized and lunges else []) + (
        [f"attack damage x{attack_damage:g}"] if attack_damage != 1.0 else []) + (
        [f"attack speed x{attack_speed:g}" + (f", {', '.join(chained)} chaining inside the stun" if chained else "")]
        if attack_speed != 1.0 else []) + (
        ["the combo's next attack on any press in its window, hit or miss (chain any, D1045)"] if chain == "any" else [])
    if armed:
        colour, why = weapon_grade(PLAYER, mode, lo, weapon_seen("own", model_scale), (colour, why)) or (colour, why)
        done = [f"the {lo.prop.title} on his {lo.weapon.style.held[0]} in {propped} LODs (W32), his staff cut from "
                f"his mesh ({' and '.join(f'{n} triangles at LOD {k}' for k, n in enumerate(cut))}, W33), the "
                f"staff's fx and power heads at its ends, {' and '.join(lo.fx_ends)}, {heads.note} (W31, W6, D618, "
                f"D707), the plain staff's head hidden ({hid} meshes, AZ-782)"
                + (f"; kept over the floor in {len(lifted)} of his clips (W41)" if lifted else "")
                + (f", through the crossfades of {len(faded)}" if faded else "")
                + ("; the balance has nothing to weigh: his own attacks" if attack_balance else ""), *done]
    own_line = (f"  Player model: {PLAYER}'s own body" + (f" drawn x{model_scale:g}" if sized else "")
                + f": {'; '.join(done + [', '.join(words.get(p, p) for p in parts)] if parts else done) or 'his own build, its sliders at 1.0'}")
    if recipe is None:
        return [own_line, f"  Player model status: {colour} ({why})"]
    from azurkit.tools.characters import _player_variants as variants
    voiced = bool(voice) and bool(recipe.drop or variant.voice != "own" or worn.sfx)
    said = _his_words(variant, worn, columns, picks, recipe_picks, reshaped, painted, styled, stride, looped,
                      toss_rows, engine) + said
    colour, why = variants.status(variant, model_scale, attack_reach, attack_damage, attack_speed)
    return [f"  Player model: {variant.name}, a variant of {PLAYER} (recipe {variant.sha}, "
            + (f"sounds {variants.sounds_sha(worn, recipe.drop)}, " if voiced else "") + f"{variant.source}): "
            + ("; ".join(said + (["its sounds (X14)"] if voiced else [])) or "its options on his own build"),
            own_line, *voice, *tail, f"  Player model status: {colour} ({why})"]


@dataclass
class _Dressed:
    """What :func:`_dress` made of a swapped body (its fields are
    :func:`apply_player_model`'s names): the config document and its
    tables, garret4's and the species' critters_engine rows, the dressed
    ``characters`` (B's clips, W17's copies, W26's carried props in), the
    body read from it, X11's fills and victories, W3's ``placed`` plan,
    W22's quiet slots, a variant's recipe columns (Step 2.137), the
    species' rows, W24's mesh plan (Step 2.142), W25's held swim, the
    columns garret4's attacks are borrowed for (Step
    2.134a), W27's swim copies (Step 2.134b), how many clips W28 turned,
    W29's rig and W28's start (the dressed archive and its TOC count) for
    its springs (Step 2.143), and what the rest of the build reads of
    them."""

    doc: object
    engine: object
    mine: dict
    theirs: dict
    characters: bytes
    body: Body
    garret4: Body
    missing_anims: str
    baked: bool
    fills: dict
    victory: dict
    anims: object
    columns: list
    cells: list
    clips: list
    picks: list
    copies: dict
    placed: tuple
    timers: bool
    quiets: dict
    recipe_picks: dict
    rows: dict
    reshaped: object
    worn: object
    swim: dict
    borrowed: int
    surfaced: dict
    styled: int = 0
    rigged: object = None
    dressed: bytes = b""
    first: int = 0
    style: Style | None = None
    """The attack style its weaponless body swings (:attr:`Loadout.kit`, Step 2.159a)."""
    take: tuple[int, float] | None = None
    """A carrier's take: the throw clip's tick her hand passes nearest her vase, and that distance (Step 2.159b)."""
    loadout: Loadout | None = None
    """What the build makes of the body's weapon (:func:`loadout`, Step 2.161a)."""
    ahead: bool = False
    """X44 in X12's attack hook's place (Step 2.161b2, AZ-688): a borrowed column's vanilla name the body owns."""
    magic: Magic | None = None
    """W34's plan where the style plays a source's own build with its graph (Step 2.161c: Balthazar's magic)."""
    cast: tuple[str, ...] = ()
    """The attack clips a creature casts his lightning in (Step 2.161e, :func:`cast_clips`; Step 2.204, on a body with
    no attack clip, the :data:`CAST_DIR` copies or ``g4/`` timers its attack columns play)."""
    painted: tuple = ()
    """W30's log lines: the textures a variant repainted (Step 2.154)."""


_KEPT_BODY: list = [None]
"""The last variant body :func:`_variant_body` made (Step 2.176): its
inputs and what it gave, pickled; a call of the same inputs takes it
instead of making it again (size_shape's dress and the build's, a
test's builds of one body: W24, W29 and W30 were half of booblord v4's
build)."""


def _kept_key(body: str, variant, folder, read, parent=None) -> tuple:
    """The key the kept body (:data:`_KEPT_BODY`) is reused on: its specs by
    ``repr``, not ``==``, since 0.0 == -0.0 and a zero's sign reaches the
    bytes (as ``mesh_edit._ray``'s memo refuses); ``parent``: the recipe
    whose jiggle places it takes (:func:`_parent_places`)."""
    return (body, repr((variant.mesh, variant.jiggle, variant.textures, variant.texture_scale)), folder, read,
            repr((parent.mesh, parent.jiggle)) if parent is not None else None)


def _parent_places(shared: tuple, _=None) -> dict:
    """W29's places of a parent recipe's jiggle bones (Step 2.177b, its
    judge's F2), {role: (origin, sides)}, as the parent's own build puts
    them: ``shared`` = (current, stored, body, its mesh, its jiggle,
    folder), its W24 and W29 on a scratch copy of ``current``.  A recipe
    ``from`` the parent whose mesh differs takes them, so finer triangles
    where her forms curve (which pull a centroid by their count) move no
    bone: her springs swing as the parent's and its clips' rests are hers.
    In a worker process while hers is planned (:func:`_variant_body`)."""
    current, stored, body, mesh, jiggle, folder = shared
    edited = bytearray(current)
    reshaped, assembled = mesh_edit.plan(stored, body, mesh, folder), None
    if reshaped.mesh is not None:
        assembled = mesh_edit.assemble(edited, reshaped, stored)
    else:
        mesh_edit.write(edited, reshaped, stored)
    rigged = jiggles.rig(edited, stored, body, jiggle, mesh, folder, asset=assembled, late=reshaped.late)
    return {pl.bone.role: (pl.origin, pl.sides) for pl in rigged.bones}


def _variant_body(current: bytes, stored: bytes, body: str, variant
                  ) -> tuple[bytes, "mesh_edit.MeshPlan | None", "jiggles.Rigged | None", list[str]]:
    """``variant``'s W24 mesh (Step 2.142), W29 jiggle bones (Step 2.143,
    D428) and W30 textures (Step 2.154) made on ``body`` in ``current``
    (the staged characters.xbr; ``stored``, the image's): the file they
    leave, the mesh plan, the rig and W30's log lines.  The last one made
    is kept (:data:`_KEPT_BODY`): a call on the same inputs (each byte of
    both files, ``body``, the recipe's ``mesh``, ``jiggle``,
    ``textures`` and ``texture_scale``, its folder and the sha256 of the one file they read
    there, ``mesh.gltf``'s) takes it, each object its own copy.  A recipe
    ``from`` another whose mesh differs places its jiggle bones where that
    one's build does (:func:`_parent_places`, Step 2.177b), and so does one
    whose shapes sized its mesh, where its build at its shapes' 1.0 does
    (Step 2.164b: her clips' rests hold); where a shipped row stands for
    those places (:func:`~azurkit.tools.characters.shipped.places`) none is worked out.
    :class:`ValueError` names the step that fails (nothing kept)."""
    import pickle

    from azurkit.tools.characters import _player_variants as variants

    folder = Path(variant.source).parent if variant.source != "built-in" else None
    gltf = variant.mesh.gltf if variant.mesh is not None else None
    read = None
    if gltf is not None and (Path(folder or ".") / gltf[0]).is_file():
        try:
            read = mesh_edit.file_sha256(Path(folder or ".") / gltf[0])
        except ValueError:   # the plan names it
            pass
    parent = variants.parent_of(variant)
    if parent is None and variant.plain is not None:   # Step 2.164b: a sized shape moves no jiggle bone
        parent = replace(variant, mesh=variant.plain, plain=None)
    if parent is None or parent.jiggle is None or variant.jiggle is None or repr(parent.mesh) == repr(variant.mesh):
        parent = None
    key = _kept_key(body, variant, folder, read, parent)
    kept = _KEPT_BODY[0]
    if kept is not None and kept[0] == key and kept[1] == current and kept[2] == stored:
        return kept[3], *pickle.loads(kept[4])
    from azurkit.tools.characters import paint, pool, shipped
    reshaped = assembled = rigged = None
    at = shipped.places(current, stored, body, parent) if parent is not None else None   # her defaults' (R3-CP1)
    placing = None if parent is None or at is not None else pool.later(   # in a child while hers is planned (Step 2.179)
        pool.each, _parent_places, (current, stored, body, parent.mesh, parent.jiggle, folder), [None], None, 1)
    edited = bytearray(current)
    try:
        if variant.mesh is not None:   # W24 (Step 2.142)
            reshaped = mesh_edit.plan(stored, body, variant.mesh, folder)
            if reshaped.mesh is not None and variant.jiggle is not None:   # a subdivided mesh: W29 rigs it, then writes
                assembled = mesh_edit.assemble(edited, reshaped, stored)
            else:
                mesh_edit.write(edited, reshaped, stored)
    except ValueError:
        if placing is not None:   # the parent's refusal first, as when its places came first
            placing.result()
        raise
    _progress.note("the mesh")   # the dress's serial stages, each a record (and a cancel point) for a call that notes them
    if placing is not None:
        at = placing.result()[0]
        shipped.heard_places(current, stored, body, parent, at)
    baking, specs = None, variant.textures
    if variant.texture_scale != 1:   # Step 2.177: every row at that many times its size
        specs = paint.scaled(stored, body, specs, variant.texture_scale,
                             reshaped.dropped if reshaped is not None else ())
    if specs or (reshaped is not None and reshaped.repaint):   # W30's bakes, in children while W29 rigs
        baking = pool.later(paint.bakes, stored, body, reshaped, specs)
    if variant.jiggle is not None:   # W29: the jiggle bones, before any reader
        rigged = jiggles.rig(edited, stored, body, variant.jiggle, variant.mesh, folder, asset=assembled, at=at,
                             late=reshaped.late if reshaped is not None else None)
        _progress.note("the springs")
    painted = []
    if baking is not None:   # W30
        painted = paint.write(edited, stored, body, reshaped, specs, baking.result())
        _progress.note("the paint")
    made = bytes(edited)
    _KEPT_BODY[0] = (key, current, stored, made, pickle.dumps((reshaped, rigged, painted), pickle.HIGHEST_PROTOCOL))
    return made, reshaped, rigged, painted


def _dress(game, species: str, mode: str, missing_anims: str | None, size: str = DEFAULT_SIZE,
           model_scale: float = 1.0, variant=None, weapon: str | None = None) -> _Dressed:
    """The body ``species`` wears in ``game``'s staged files in gameplay
    ``mode`` with X11's ``missing_anims`` rule (``None``: the mode's) at
    ``size`` drawn ``model_scale`` times it, as :func:`apply_player_model`
    dresses it before W1: its picks and W3's plan, B's baked clips (a body
    with no clips' at its drawn scale, Step 2.127; the roll drawn about its
    centre there, Step 2.133), W17's copies and W26's
    carried props, and a ``variant``'s recipe (Step 2.137: its columns' clips,
    W22's grown markers and v/ clips; first W24's mesh, Step 2.142; with
    none, in own mode, the species' own-build overlay, W23, Step 2.140),
    written into ``game``'s characters.xbr and index.xbr, ``weapon``
    the one picked (:func:`loadout`, Step 2.161b: W31's carriers before
    any reader, W33 where W26 runs; W32's mesh is
    :func:`apply_player_model`'s, after W28; Step 2.161e: a creature's
    cast, :func:`cast_clips`, and on a creature or token W31 there too,
    after every measure of its pose).
    :func:`size_shape` dresses a scratch copy with it, so the size the
    fold reads is the one the build's camera and touch use (2.133's
    critique, finding 2)."""
    from azurkit.tools.characters import _player_variants as variants
    doc = _load_doc_for_edit(game, "config.xbr")
    engine = doc.keyed_section("critters_engine")
    # The image's cells: a pack's enemy or boss size (enemy_scaling) resizes that creature, not its wearer.
    rows = _species(XbrDocument.from_bytes(game.stored("config.xbr")).keyed_section("critters_engine"))
    mine, theirs = rows[PLAYER], rows[species]
    characters = game.stored("characters.xbr")
    body = read_body(characters, theirs["body"])
    reshaped = rigged = None
    painted = []
    if variant is not None and (variant.mesh is not None or variant.jiggle is not None or variant.textures):
        try:   # W24, W29 and W30: first, so every reader measures them
            made, reshaped, rigged, painted = _variant_body(bytes(game["characters.xbr"]), characters, body.name,
                                                            variant)
        except ValueError as exc:   # the shapes it was built at named (Step 2.164b's review D1)
            sized = ", ".join(f"{s.title} {s.value:g}" for s in variant.shapes if s.value != 1.0)
            raise ValueError(f"--player-character {variant.name!r} (a variant of {species})"
                             + (f" at {sized}" if sized else "") + f": {exc}") from None
        game["characters.xbr"] = bytearray(made)
        characters = made
        if variant.lods is not None:   # W39's cuts (and none of W36's: its LODs leave the shadow nothing to cut)
            _lods_ahead(made, body.name, variant.lods)
        else:
            _shadow_ahead(made, engine, mine["body"], body.name, variant.shadow)
    garret4 = read_body(characters, PLAYER)
    # the mode's rule (Step 2.73a); a clipless body's only clips are
    # garret4's, whatever is asked
    if missing_anims is None or not body.clips:
        missing_anims = MODE_ANIMS[mode] if body.clips else "garret4"
    baked = bakes(body, missing_anims)
    floating = floats(species, mode, baked)   # a baked flyer's air, slide, swims and roll its own (D334, D335)
    # its weapon (Step 2.161a, D492-D495): a baked farmer swings garret4's attacks with its hoe (Step 2.134a);
    # a townsperson with no weapon the bare-hands kit (Step 2.159a, D471), a variant of one in the columns its
    # recipe leaves; a variant of a farmer keeps its base's own picks; a picked one (Step 2.161b) its own
    try:
        lo = loadout(characters, body, mode, baked, variant, weapon)
        if lo.carry == COPY:   # W31 (Step 2.161b): its prop's carriers under its grip, after W24's and W29's bones
            edited = add_carriers(characters, body, lo, Retarget(characters, body.name, grow=False))
            game["characters.xbr"] = bytearray(edited)
            characters, body = edited, read_body(edited, body.name)
    except ValueError as exc:
        raise ValueError(f"--player-character {species!r}: {exc}") from None
    dressed, first = bytes(game["characters.xbr"]), len(parse_toc(characters))   # W28's start: the clips added after
    # the recipe the build plays: a variant's (Step 2.161g, D585: its moveset dropped under another weapon), a
    # moveset weapon's laid over the body (D592), or W23 (Step 2.140, D374) the species' own-build overlay, worn
    # only with its own weapon (the 2.161 design's L6)
    worn = (lo.recipe if lo.recipe is not None else variant if variant is not None
            else variants.overlay(species) if mode == "own" and not lo.picked else None)
    who = (f"{variant.name!r} (a variant of {species})" if variant is not None
           else f"{species!r} (with {lo.weapon.title})" if lo.lent
           else f"{species!r} (its own build's {', '.join(sorted(worn.clips)) or 'fx'})" if worn is not None else None)
    style, borrowing = lo.kit, lo.borrowing
    caster = lo.cast or style   # Step 2.161e: a creature's cast plays his graph on the clone too
    if caster is not None and caster.fx is not None and worn is not None and worn.fx_edits:   # L12
        raise ValueError(f"--player-character {who}: its weapon {lo.name} plays {caster.source}'s graph on the "
                         "player's clone (W34), and its recipe's fx edit a clone of the body's own (X40 binds one "
                         "key)")
    # Balanced's base idle: the body's calmest looping one where its chain's moves twice as fast (D331);
    # a recipe's idles name it themselves (Step 2.168)
    calm = calm_idle(characters, body) if mode == "own" and not (worn is not None and worn.idles) else None
    himself = body.name == PLAYER   # Step 2.161d: his own rig wearing a style; his slots and victories stay his
    fills = slot_fills(body, garret4, missing_anims, baked=baked, calm=calm, floats=floating) if not himself else {}
    # W25 (Step 2.134a, D341, D419): guard_air's swim somersaults once, then bobs in its barrel (Balanced)
    swim, swim_clips = held_swim(characters, body, fills) if mode == "own" else ({}, {})
    fills |= swim
    victory = victory_fills(body, garret4, baked=baked) if not himself else {}   # X11's victories (Step 2.121)
    slotted = recipe_fills(worn.slot_clips()) if worn is not None else {}   # its slots (Step 2.171): before B,
    fills = {k: v for k, v in fills.items() if k not in slotted} | {     # so no garret4 clip they replace bakes
        k: v for k, v in slotted.items() if k not in VICTORIES}
    victory |= {k: v for k, v in slotted.items() if k in VICTORIES}
    stand = "idle" if "idle" in body.clips else fills.get(1, (None, 0.0))[0]   # what its idle slot plays
    anims = doc.keyed_section("attacks_anims")
    columns = anims.col_names()
    cells = [anims.find_cell(col, "Anim", i) for i, col in enumerate(columns)]
    clips = [cell.string_value for cell in cells]   # garret4's, before W3
    strings = anim_strings(anims)
    picks = (list(clips) if himself else
             substitutes(columns, body, baked, strings if baked and mode == "garret4" or borrowing else None,
                         floats=floating, borrow=borrowing) if body.clips else [])
    if style is not None:
        picks = style_picks(style, columns, picks)
    if himself and model_scale != 1.0:   # E (Step 2.133, AZ-608), as his own build's: his roll about his centre
        try:
            if sized_roll(game, characters, body, model_scale):
                characters = bytes(game["characters.xbr"])
                body = read_body(characters, body.name)
                picks[columns.index(ROLL)] = SIZED_ROLL
        except ValueError as exc:
            raise ValueError(f"{_named(PLAYER)}: {exc}") from None
    recipe_picks: dict[int, str] = {}
    if worn is not None:   # its recipe's columns (Step 2.137): its v/ clips or base clips, the rest W3's picks
        why_not = variants.refusal(worn, rows, columns, body) or (None if picks else f"{body.name} has no clips")
        if why_not:
            raise ValueError(f"--player-character {who}: {why_not}")
        picks = [worn.clip_of(col) or pick for col, pick in zip(columns, picks)]
        recipe_picks = {i: p for i, p in enumerate(picks) if worn.clip_of(columns[i])}
    # D as W2 writes it below (the bake and W26 leave the mesh's height, which size_scale reads, as it
    # is): a body with no clips' root rides garret4's m_feet / D (Step 2.127, AZ-562), and its baked
    # roll and lunges are drawn about its centre there (Step 2.133, AZ-608; Step 2.175, AZ-623)
    drawn = drawn_scale(size_scale(characters, body) if size == "garret4" else None, mode, theirs["scale"],
                        model_scale)
    # W17 (Step 2.75e, AZ-453): a pick that switches on its body's own
    # damage field plays a copy without that switch, W3 alone naming it;
    # own body plays the clip itself, X37 turning the field on its target (Step 2.135, D324);
    # W22 (Step 2.175, AZ-611): one that starts its scripted fx (fire_guardian's shards) a copy without it, in every mode;
    # and a lunge drawn about its centre at D != 1 (Step 2.175, AZ-623)
    copy_picks, quieted = list(picks), scripted_switches(characters, body.name)
    copied = attack_copies(characters, body, copy_picks, mode, drawn, quieted)
    w3 = set(copied)   # the clips W3 copies for themselves; the roll plays a CAST_DIR copy of none of the rest
    copying = lo.cast is not None and bool(body.clips) and not attack_clips(body)   # Step 2.204 (D810): no attack
    if copying:   # clip of its own to cast in: W3 names a copy of each clip its attack columns play (CAST_DIR)
        copied = with_casts(characters, body, columns, copy_picks, copied)
    copies = {clip: name for clip, (name, _) in copied.items()}
    # garret4's attacks a borrowing build swings: W3 leaves their vanilla Anims, the roll's too, which
    # X12's ATTACK lookup resolves to the baked g4/ clips (Step 2.134a), X44's where the body owns a name
    # (Step 2.161b2, AZ-688: under X12 keylord's attack_1 played his own); since Step 2.161g (D585) a weapon
    # borrowing them drops a recipe's columns, so no recipe column names that clip of the body's beside them
    borrowed = sum(1 << i for i, col in enumerate(columns) if borrowing and col != ROLL and i not in recipe_picks)
    kept = borrowed | (1 << columns.index(ROLL) if borrowing else 0)
    names = {strings[i].value.casefold() for i, col in enumerate(columns) if kept >> i & 1}   # as the game
    owned = names & {clip.casefold() for clip in body.clips}   # looks a name up
    named = [strings[i].value if kept >> i & 1 else p if columns[i] == ROLL and p not in w3 else copies.get(p, p)
             for i, p in enumerate(picks)]   # the roll its clip as it was, never the cast's copy (Step 2.204)
    try:   # W3's plan (written below), which may move a pick (spideyzar's whirlwind)
        plan = place_anims(columns, strings, named) if picks else ({}, [])
    except ValueError as exc:
        raise ValueError(f"--player-character {species!r}: {exc}") from None
    plain = {name: clip for clip, name in copies.items()}
    picks = [BAKED_DIR + p if kept >> i & 1 else plain.get(p, p) for i, p in enumerate(named)]
    lost = [columns[i] for i, p in (recipe_picks.items() if worn is not None else ()) if picks[i] != p]
    if lost:   # place_anims' second rule gave its string to another clip
        raise ValueError(f"--player-character {who}: attacks_anims has no string for its "
                         f"{', '.join(lost)} as its recipe asks")
    timers = not body.clips    # B as timers, and X12's lookup for the attacks_anims columns
    # B (Step 2.87; D226, D238): garret4's clips baked onto its rig, the roll's too; on a body
    # whose other clips are its own, his victories alone, its markers its own (Step 2.121, D299)
    wanted = {c[len(BAKED_DIR):] for c in [c for c, _ in (*fills.values(), *victory.values())] + picks
              if c.startswith(BAKED_DIR)}
    if timers:
        wanted |= {cell.string_value for cell in cells if cell.string_value in garret4.clips}
    rolled = {G4_ROLL} if picks and picks[columns.index(ROLL)] == BAKED_DIR + G4_ROLL else set()
    lunged = {p[len(BAKED_DIR):] for i, p in enumerate(picks) if p.startswith(BAKED_DIR) and columns[i] != ROLL
              and moves_root(characters, PLAYER, p[len(BAKED_DIR):])}   # garret4's lunges baked (AZ-623)
    styled_clips = sorted({p[len(style.dir):] for p in picks if p.startswith(style.dir)}) if style else []
    try:   # Step 2.159a: a prop its stand clip shows (town_female_4's vase) carried on its head in every baked
        # clip, B's and the style's, so it never pops in and out with an attack
        props = kit_carried(characters, body, style.source, stand) if styled_clips and not himself else {}
        rig = Rig.read(characters, body.name) if props else None
    except ValueError as exc:
        raise ValueError(f"--player-character {species!r}: {exc}") from None
    kept_on = (lambda _name, _source, clip: kit_carry(rig, clip, props)) if props else None
    styled_on, took = kept_on, {}
    if props and style.throw is not None and style.throw.clip in styled_clips:   # Step 2.159b (D473): she takes the
        def styled_on(name: str, _source, clip):   # vase off her head into the throw and it comes back to her hand
            if name != style.throw.clip:
                return kit_carry(rig, clip, props)
            took["take"] = take = throws.take_tick(rig, clip, props, style.throw)
            return throws.throw_carry(rig, clip, props, take[0], style.throw.back)
    if lo.carry == COPY and not baked:   # the lift the bake gives its clips, where the copy's tips read them
        lo = replace(lo, lift=Retarget(characters, body.name, grow=False, stand=stand).lift)
    if baked or wanted:
        try:
            grown, index = bake_body(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body.name, wanted,
                                     grow=baked, stand=None if baked else stand, drawn=drawn, centre=rolled,
                                     lunges=lunged,
                                     lift=BAKED_LIFTS.get(body.name.casefold(), 0.0) if baked else 0.0,
                                     post=(carried(characters, body, lo) if lo.carry == IN_PLACE else
                                           carried_copy(characters, body, lo, variant) if lo.carry == COPY else kept_on))
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
        game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
        # every check below reads the grown body, the markers it gained
        # included: with m_grab it needs no X9
        characters, body = grown, read_body(grown, body.name)
    dirs = ((style.dir,) if styled_clips else ()) + ((SELF_DIR,) if SIZED_ROLL in picks else ())   # his sized roll
    spells = None
    if styled_clips and style.fx is not None:   # W34 (Step 2.161c): M1, the markers his graph binds grown on the
        # body before his clips bake, so they keep his tracks; S6, those his effects hang under ridden on its hand
        try:
            spells = magic(characters, body, style, game.stored("default.xbe"))
            if spells.grown:
                grown, index = add_clips(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body.name, {},
                                         markers=spells.grown)
                game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
                characters, body = grown, read_body(grown, body.name)
            ridden, kit_on = ride(characters, body, style, spells), styled_on
            if ridden is not None:
                styled_on = (lambda name, source, clip: ridden(name, source, kit_on(name, source, clip))) if kit_on \
                    else ridden
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if styled_clips:   # Step 2.159a: the style's clips baked onto its rig, <dir><clip>, without boxes (X3's at
        # its hand), a prop its stand clip shows carried where it shows it (town_female_4's vase on her head)
        try:
            grown, index = bake_body(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body.name,
                                     styled_clips, grow=False, drawn=drawn, lender=style.source, into=style.dir,
                                     quiet_markers=DAMAGE_MARKERS, given=style.clips(characters), post=styled_on)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
        game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
        characters, body = grown, read_body(grown, body.name, dirs=dirs)
    if spells is not None:   # W34: the player's clone of his graph, his own build's retune, a bone bind renamed
        # to the body's bone of its role; X40 binds it to the player, so W16, W22, X37 and X38 read it from here
        try:
            new = magic_graph(characters, body, style, spells, game.stored("default.xbe"), game.stored("fx.xbr"))
            grown = append_resources(bytes(game["characters.xbr"]), new)
            index = add_index_records(bytes(game["index.xbr"]), [IndexRecord(r.name, "characters.xbr", r.tag)
                                                                 for r in new if r.name is not None])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: W34: {exc}") from None
        game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
        characters = grown
    cast = ()
    if lo.cast is not None:   # W34 on a creature (Step 2.161e): M1 on its body, his lightning cast from its grip in
        # its own attack clips (in place), the player's clone of his graph; its own boxes hit
        try:
            spells = magic(characters, body, lo.cast, game.stored("default.xbe"))
            if spells.grown:
                grown, index = add_clips(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body.name, {},
                                         markers=spells.grown)
                game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
                characters, body = grown, read_body(grown, body.name, dirs=dirs)
            if copying:   # Step 2.204 (D810): in the copies of its columns' clips, keyed below
                grown = bytes(game["characters.xbr"])
            else:   # its own attack clips in place, or (Step 2.204) a clipless body's g4/ timers its columns play
                grown, cast = cast_clips(bytes(game["characters.xbr"]), body, lo.cast, spells, None if body.clips else
                                         tuple(sorted(BAKED_DIR + c for c in cast_picks(columns, clips)
                                                      if c in garret4.clips)))
            new = magic_graph(grown, body, lo.cast, spells, game.stored("default.xbe"), game.stored("fx.xbr"))
            grown = append_resources(grown, new)
            index = add_index_records(bytes(game["index.xbr"]), [IndexRecord(r.name, "characters.xbr", r.tag)
                                                                 for r in new if r.name is not None])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
        game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
        characters, body = grown, read_body(grown, body.name, dirs=dirs)
        if copied:   # the cast rewrote the clips W3's copies were taken from: take them again, the same names
            copied = attack_copies(characters, read_body(characters, body.name), copy_picks, mode, drawn, quieted)
        if copying:   # Step 2.204: the copies of its columns' clips taken from the grown body, the cast keyed in them
            targets = cast_picks(columns, copy_picks)
            copied = cast_copies(characters, body, lo.cast, spells,
                                 with_casts(characters, body, columns, copy_picks, copied), targets)
            cast = tuple(sorted(name for pick, (name, _) in copied.items() if pick in targets))
    victory_clips = victory_copies(characters, body, garret4, field_switches(characters, body.name)   # D300
                                   | scripted_switches(characters, body.name))   # and W22's (AZ-611)
    # W22 (Step 2.131, AZ-603, D343): a slot whose clip starts the body's scripted fx (a boss's
    # death camera and drop) plays a copy without that marker, X11 naming it
    quiets, quiet_clips = quiet_fills(characters, body, fills | victory,
                                      idle_fills(worn.idle_clips()) | slotted if worn is not None else ())
    if copies or victory_clips or quiet_clips or swim_clips:   # W17's copies, after B's clips: the marker indices they keep hold on a grown body
        try:
            grown, index = add_clips(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body.name,
                                     dict(copied.values()) | victory_clips
                                     | quiet_clips | swim_clips)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
        game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
        characters = grown
    # W27 (Step 2.134b, AZ-638): a baked body without m_root swims with its root at the centre, as garret4
    # does; after B, so no baked clip carries his m_root tracks (the ladder's and the hang's samples stay 0)
    try:
        surfaced, surface_clips = surfaced_swim(characters, body, fills, drawn)
        if surface_clips:
            record = dict(marker_records(characters, PLAYER))[SURFACE_MARKER]
            grown, index = add_clips(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body.name,
                                     surface_clips, markers=[(SURFACE_MARKER, record),
                                                             (SURFACE_EYE, (0.0, 0.0, 1.0, *record[3:]))])
            game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
            characters, body = grown, read_body(grown, body.name, dirs=dirs)
            fills |= surfaced
    except ValueError as exc:
        raise ValueError(f"--player-character {species!r}: {exc}") from None
    if lo.lent:   # Step 2.161g (D592): a moveset's markers the body has of its own already (garret4's m_damage) its own
        have = {m.casefold() for m in body.markers}
        worn = replace(worn, markers=tuple(m for m in worn.markers if m.casefold() not in have))
    if worn is not None:   # W22 (Step 2.137): its markers grown after B (C5), its clips under v/
        try:
            grown, index = variants.grow(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body, worn,
                                         game.stored("default.xbe"), game.stored("fx.xbr"))
        except ValueError as exc:
            raise ValueError(f"--player-character {who}: {exc}") from None
        game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
        characters, body = grown, variants.reread(grown, body, dirs)   # every check below reads its clips
        if worn.idles:   # X11's idle slots (Step 2.168, D553): its base loops, its fidgets play once (X45)
            idles = worn.idle_clips()
            seam = base_seam(characters, body.name, idles["idle"])
            if seam > CALM_SEAM:
                raise ValueError(f"--player-character {who}: idles.idle: {idles['idle']} doesn't end where it starts "
                                 f"(seam {seam:.3f} > {CALM_SEAM:g} model units), so it can't loop as the base")
            fills |= idle_fills(idles)
        gait_checks(characters, body, worn, who)
        move_checks(characters, body, worn, who)
    try:   # W26 (Step 2.134b, D337): a prop on the body's root (the farmers' hoe) on its staff carrier; W33
        # (Step 2.161b): hidden, a farmer wearing another weapon
        held = carry_props(game["characters.xbr"], body, lo) if lo.carry == IN_PLACE else 0
        held += hide_own(game["characters.xbr"], body, lo) if lo.hide else 0
    except ValueError as exc:
        raise ValueError(f"--player-character {species!r}: {exc}") from None
    if held:
        characters = bytes(game["characters.xbr"])
    if rigged is not None and any(pl.bone.spring is None and not pl.bone.keyed for pl in rigged.bones):
        rated = rate_copies(body, fills)   # W28 (AZ-648): a clip a walk and a run slot both play, the run slots'
        # copy (X41's rows need none, nor a keyed bone)
        if rated:
            try:
                grown, index = add_clips(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body.name, {
                    name: named_clip(characters, body.name, name[len(RATE_DIR):]) for name, _ in rated.values()})
            except ValueError as exc:
                raise ValueError(f"--player-character {who}: {exc}") from None
            game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
            characters = grown
            fills |= rated
    styled = 0
    if variant is not None and (variant.arms or variant.arm_clips or variant.poses):   # W28 (Step 2.143, D428): every
        # clip's arms (and a recipe's poses, Step 2.154), each once
        try:
            grown, styled, _ = variants.restyled(dressed, bytes(game["characters.xbr"]), first, body.name, variant)
        except ValueError as exc:
            raise ValueError(f"--player-character {who}: {exc}") from None
        game["characters.xbr"] = bytearray(grown)
        characters = grown
    return _Dressed(doc, engine, mine, theirs, characters, body, garret4, missing_anims, baked, fills, victory,
                    anims, columns, cells, clips, picks, copies, plan, timers, quiets, recipe_picks,
                    rows, reshaped, worn, swim, borrowed, surfaced, styled, rigged, dressed, first,
                    style if styled_clips else None, took.get("take"), lo, bool(owned), spells, cast, tuple(painted))


TWIN_SHARE = 0.05
"""How far a backward gait's planted speed may sit from its forward twin's,
as a share of the twin's (:func:`gait_checks`): one cell times both."""


def gait_checks(characters: bytes, body: Body, variant, who: str) -> dict[str, float]:
    """The planted speeds (:func:`planted`) of the gait clips ``variant``'s
    ``slots`` names (Step 2.171), by slot name, each played in a loop at
    the rate W7 times by its forward twin's: :class:`ValueError` names one
    that doesn't end where it starts (:data:`CALM_SEAM`), a forward one
    whose planted feet don't move back (:data:`PLANT_MIN`: W7 can't time
    it) and a backward one whose planted feet don't move forward within
    :data:`TWIN_SHARE` of its twin's speed: 0x30D90 plays both at a
    positive rate, so the backward clip's own keys must walk it back, as
    garret4's walk_backwards and run_backwards do (D35)."""
    clips, speeds = variant.slot_clips(), {}
    for slot in ("walk", "run", "walk_backwards", "run_backwards"):
        if slot not in clips:
            continue
        clip, why = clips[slot], f"--player-character {who}: slots.{slot}: "
        seam = base_seam(characters, body.name, clip)
        if seam > CALM_SEAM:
            raise ValueError(f"{why}{clip} doesn't end where it starts (seam {seam:.3f} > {CALM_SEAM:g} model "
                             "units), so it can't loop")
        speed = planted(characters, body.name, clip)
        twin = GAIT_TWINS.get(slot)
        if twin is None and not (speed and speed >= PLANT_MIN * bind_height(characters, body.name)):
            raise ValueError(f"{why}{clip} plants no foot that moves back (at least {PLANT_MIN:g} of its height a "
                             "second), so W7 can't time it")
        if twin is not None and (speed is None or speed >= 0.0
                                 or abs(-speed - speeds[twin]) > TWIN_SHARE * speeds[twin]):
            raise ValueError(f"{why}{clip}'s planted feet move {speed or 0.0:+.3f} model units a second (+ back), not "
                             f"{-speeds[twin]:+.3f} within {TWIN_SHARE:.0%} (slots.{twin}'s {clips[twin]}, run "
                             "backwards): one cell times both")
        speeds[slot] = speed
    return speeds


def move_checks(characters: bytes, body: Body, variant, who: str) -> None:
    """A victory, jump or landing ``variant``'s ``slots`` names (Steps 2.171,
    2.164c, 2.193) plays as it is (X11, no W22 or D300 quiet copy), so
    :class:`ValueError` names one whose clip keys above 0 a damage marker
    (:data:`DAMAGE_MARKERS`), a switch of its body's own damage field
    (:func:`field_switches`) or of its scripted fx (:func:`scripted_switches`):
    a victory and a landing are harmless (D300, D35), and so is a jump, as
    garret4's (the jump attack is a column); and a touchdown that doesn't
    last garret4's :data:`TOUCHDOWN_TICKS` (the hard landing holds the
    player for its clip: D35, his timing kept)."""
    switches = set(DAMAGE_MARKERS) | field_switches(characters, body.name) | scripted_switches(characters, body.name)
    jumps = {BASE_CLIPS[k] for k in JUMPS}
    for slot, clip in variant.slot_clips().items():
        if not slot.startswith("victory_") and slot not in jumps and slot != "touchdown":
            continue
        made = named_clip(characters, body.name, clip)
        keyed = sorted({body.markers[t.target] for t in made.markers
                        if body.markers[t.target] in switches and any(key[1] > 0 for key in t.keys)})
        if keyed:
            kind = "a jump" if slot in jumps else "a landing" if slot == "touchdown" else "a victory"
            raise ValueError(f"--player-character {who}: slots.{slot}: {clip} keys {', '.join(keyed)} above 0, which "
                             f"{kind} never does (D300: it is harmless)")
        if slot == "touchdown" and round(made.length * 30.0) != TOUCHDOWN_TICKS:
            raise ValueError(f"--player-character {who}: slots.touchdown: {clip} lasts {made.length:.3f} s, not "
                             f"garret4's {TOUCHDOWN_TICKS} ticks ({TOUCHDOWN_TICKS / 30.0:.3f} s): a hard landing "
                             "holds the player for its clip")


RATE_DIR = "r/"
"""Where W28 puts the run slots' copy of a clip a walk slot plays too
(Step 2.143, AZ-648): ``characters/<body>/r/<clip>``, keyed at the run
slot's rate, the clip itself at the walk slot's (:func:`rate_copies`)."""
WALK_SLOTS, RUN_SLOTS = (8, 13), (9, 14)
"""The base slots whose clip 0x30D90 plays at the speed over (the drawn
scale x ``walkAnimSpeed``), and x ``runAnimSpeed`` (walk, walk_backwards;
run, run_backwards: ``docs/RE_XBE.md``)."""
WALK_SHARE = 0.8
"""The speed W29's springs are baked at in the walk slots, a share of
garret4's ``walkSpeed`` (:data:`WALK_SPEED`, the walk/run switch; 5.0 m/s
at x1): 4.0 m/s, between half tilt's 3.5 and the switch, so no walk on
flat ground plays the bake over 1.25 times its rate (a slope's walk plays
at :data:`RUN_SPEED` x the stick, 0x89C2F [inferred]: up to 1.75 times).
The run slots' speed is his :data:`RUN_SPEED`, the full-tilt run."""
RUN_SPEED = "runSpeed"
"""garret4's ``critters_critter_data`` cell (CritterData +0x40) the walk
state moves the player at, times the stick: 7.0 m/s at the walk slider's 1,
x ``player_physics``' ``walk_speed_scale`` (and the size fold's sqrt(s))."""
STEP_RATE = 3.0
"""step_up's (slot 53) rate at full tilt: 2.8 x the stick's magnitude +
0.2, at least 1 (0x8B65F, its 0x30940 at 0x8B6CD)."""
CLIMB_LOOPS, CLIMB_RATE = tuple(BASE_CLIPS.index(c) for c in ("climb_up", "climb_down", "climb_left", "climb_right")), 2.0
"""The climb loops' (slots 56-59) rate at full tilt: 0x1980E4's 2.0 x the
stick (0x88357, 0x30940 at 0x883D7); climb_idle (55) plays at 1."""
ALIGNED_SLOTS, ALIGNED_RATE = (60, 62, 63, 64, 65, 66), 1.5
"""The ladder's latches and top and the ledge hoists, which the move-state
setter's callers set to 0x1980E0's 1.5 through 0x30940 (0x870F7,
0x87929, 0x87F55, 0x87444, 0x86D9E)."""


def rate_copies(body: Body, fills: dict[int, tuple[str, float]]) -> dict[int, tuple[str, float]]:
    """W28's fills for the run slots (:data:`RUN_SLOTS`) whose clip a walk
    slot (:data:`WALK_SLOTS`) plays too, by X11's ``fills`` or by name: its
    :data:`RATE_DIR` copy, timed as the fill was (Step 2.143, AZ-648: the
    run slot plays her walk at 1.217 clip seconds a second at 7 m/s, the
    walk slot at 4.7-6.6 between 3.5 and 4.9 m/s, so one set of keys
    can't fit both)."""
    plays = {k: c for k, n in enumerate(BASE_CLIPS) for c in body.clips if c.casefold() == n} | {
        k: c for k, (c, _) in fills.items()}
    walks = {plays[k] for k in WALK_SLOTS if k in plays}
    return {k: (RATE_DIR + plays[k], fills.get(k, (plays[k], 0.0))[1]) for k in RUN_SLOTS if plays.get(k) in walks}


def playback_rates(characters: bytes, doc, body: Body, slots: dict[int, tuple[str, float]], picks: list[str],
                   drawn: float, hit: bool) -> dict[str, float]:
    """How fast (clip seconds a real second) the game plays each clip
    under ``body`` (Step 2.143, AZ-648), by its name there (casefolded),
    from ``doc``'s cells as the build wrote them: in the walk and run slots
    the speed (:data:`WALK_SHARE` x his :data:`WALK_SPEED`, his
    :data:`RUN_SPEED`) over the drawn scale x garret4's ``walkAnimSpeed``
    / ``runAnimSpeed`` (0x30D90; none: 1),
    step_up :data:`STEP_RATE`, the climb loops :data:`CLIMB_RATE`, the
    ladder's moves and the hoists :data:`ALIGNED_RATE`, a garret4-timed
    fill (X12) its length over the time it plays in, with ``hit`` (X7)
    slot 37's clip, which plays in every hit slot, its length over
    garret4's 0.4 s, each attack column's clip its ``Rate``, any other
    slot 1; ``slots`` X11's table (fills, victories, quiets), each slot it
    doesn't name playing the body's clip of that name.  A clip several
    play at different rates takes their geometric middle, so none plays
    it more than the root of their spread off.  X9's stand-ins (a body
    without the climb's clips) and X7's fallbacks keep their own slots'
    rates."""
    data, anims = doc.keyed_section("critters_critter_data"), doc.keyed_section("attacks_anims")
    cells = _doubles(data, PLAYER, (*_STRIDE, WALK_SPEED, RUN_SPEED))
    plays = {k: c for k, n in enumerate(BASE_CLIPS) for c in body.clips if c.casefold() == n} | {
        k: c for k, (c, _) in slots.items()}
    timed = {k: t for k, (_, t) in slots.items() if t > 0}
    rates: dict[str, list[float]] = {}

    def length(name: str) -> float:
        return named_clip(characters, body.name, name).length

    def stride(cell: float | None, speed: float | None) -> float:
        return speed / (drawn * cell) if cell and speed and speed > 0 and drawn > 0 else 1.0
    for k, name in plays.items():
        if hit and k in HIT:
            continue
        rate = (stride(cells[_STRIDE[0]], WALK_SHARE * (cells[WALK_SPEED] or 0.0)) if k in WALK_SLOTS
                else stride(cells[_STRIDE[1]], cells[RUN_SPEED]) if k in RUN_SLOTS
                else STEP_RATE if k == BASE_CLIPS.index("step_up") else CLIMB_RATE if k in CLIMB_LOOPS
                else ALIGNED_RATE if k in ALIGNED_SLOTS else length(name) / timed[k] if k in timed else 1.0)
        rates.setdefault(name.casefold(), []).append(rate)
    ouch = plays.get(BASE_CLIPS.index("ouch_1"))
    if hit and ouch is not None:   # X7's clip in every hit slot (its fallbacks keep their own slots' rates)
        rates.setdefault(ouch.casefold(), []).append(length(ouch) / HIT_SECONDS.default)
    columns = anims.col_names()
    for i, (col, pick) in enumerate(zip(columns, picks)):
        cell = anims.find_cell(col, "Rate", i)
        rates.setdefault(pick.casefold(), []).append(cell.double_value if cell is not None else 1.0)
    return {name: math.sqrt(min(r) * max(r)) for name, r in rates.items()}


def _jiggle_line(rigged, peaks: dict, variant, sprung: list | None = None, strength: float = 1.0,
                 stiffness: float = 1.0) -> str:
    """W29's part of the variant's log line, with W28's baked springs and
    X41's real-time ones (Step 2.156)."""
    def spring(pl) -> str:
        if pl.bone.keyed:
            return "keyed by its own clips"
        if pl.bone.spring is None:
            return f"its spring {pl.bone.freq:g} Hz baked"
        s = pl.bone.spring
        at = f"{s.freq:g} Hz" if s.freq is not None else f"{s.stiffness:g} N/m over {s.mass:g} kg"
        return f"a real-time spring of {at}, damping {s.damping:g} (X41)"
    bones = "; ".join(f"{pl.bone.role} on {pl.bone.bone} (under {pl.bone.parent}, {sum(pl.reach.values())} vertices "
                      f"up to {pl.largest:.2f}, {spring(pl)})" for pl in rigged.bones)
    baked = [pl for pl in rigged.bones if pl.bone.spring is None and not pl.bone.keyed]
    most = {pl.bone.role: max(((v[pl.bone.role][0], k) for k, v in peaks.items() if pl.bone.role in v),
                              default=(0.0, "-"))   # a recipe clip that keys a bone bakes none (Step 2.168)
            for pl in baked}
    added = f", {rigged.added} added" if rigged.added else ""
    resting = [r.role for r in sprung or () if r.coeffs.rests]
    return (f"its jiggle (W29): {bones}; {rigged.emptied} palette entries freed{added}, {rigged.folded} fourth "
            f"weights folded (up to {rigged.fold_largest:.3f})"
            + (f"; keyed in {len(peaks)} clips (W28), "
               + ", ".join(f"the {r} at most {d:.3f} model units in {c}" for r, (d, c) in most.items())
               + (f"; still in {', '.join(variant.jiggle.still)}" if variant.jiggle.still else "") if baked else "")
            + (f"; real-time springs on {', '.join(b.bone for b in variant.jiggle.springs)}"
               if variant.jiggle.springs else "")
            + (f"; X41 drives {len(sprung)} in game at strength {strength:g}, stiffness {stiffness:g}"
               + (f" (the {', '.join(resting)} at rest: its springs' coefficients at that stiffness aren't "
                  "finite)" if resting else "") if sprung and strength != 0.0
               else f"; strength 0: no X41, the {', '.join(r.role for r in sprung)} rigid" if sprung else ""))


def _hair_line(sprung: list, strength: float, stiffness: float) -> str:
    """The build-log line of a body's hair on X41 (Step 2.169f, chains.json)."""
    links = ", ".join(r.role + (f" ({r.spring.freq:g} Hz)" if r.spring.freq is not None else "") for r in sprung)
    stops = sorted({r.spring.wall[3] * 1000.0 for r in sprung if r.spring.wall is not None})
    walled = f", walled {'/'.join(f'{w:g}' for w in stops)} mm off the clip's pose toward its head" if stops else ""
    return (f"  Player model hair: X41 swings its {len(sprung)} links on real-time springs (chains.json): {links}"
            f"{walled}; strength {strength:g}, stiffness {stiffness:g}" if strength != 0.0 else
            f"  Player model hair: strength 0: no X41, its {len(sprung)} links (chains.json) as the clips pose them")


def _slots_line(variant, stride: dict[str, float]) -> str:
    """The variant's slots' part of its log line (Step 2.171)."""
    slots: dict[str, list[int]] = {}
    for name, clip in variant.slot_clips().items():
        slots.setdefault(clip, []).append(BASE_CLIPS.index(name))
    played = ", ".join(f"{clip} in slot{'s' * (len(k) > 1)} {', '.join(map(str, k))}" for clip, k in slots.items())
    timed = [f"{prop} {stride[prop]:.3f}" for prop, slot in zip(_STRIDE, STRIDE_SLOTS)
             if BASE_CLIPS[slot] in variant.slots and prop in stride]
    return f"its slots (X11): {played}" + (f"; W7 times its gait by its planted feet ({', '.join(timed)})"
                                           if timed else "")


def _idles_line(variant) -> str:
    """The variant's idles' part of its log line (Step 2.168, D553)."""
    slots: dict[str, list[int]] = {}
    for name, clip in variant.idle_clips().items():
        slots.setdefault(clip, []).append(BASE_CLIPS.index(name))
    played = ", ".join(f"{clip} in slot{'s' * (len(k) > 1)} {', '.join(map(str, k))}" for clip, k in slots.items())
    lo, hi = variant.idle_wait
    mask = fidget_mask(variant.idle_clips())
    return (f"its idles (X11): {played}" + (
        f"; a fidget after {lo:g}-{hi:g} s of standing (10 at least, the game's own check), never one twice in a "
        f"row (X45, {mask.bit_count()} fidgets)" if mask else "; no fidget, so no X45"))


def _reshaped_line(plan, variant, rows: dict, species: str, restored: bool = False) -> str:
    """W24's part of the variant's log line: what its mesh moved, and who
    else wears the body (whose NPCs keep vanilla's mesh where P2
    ``restored`` the body, Step 2.203)."""
    edit = plan.gltf
    by = ([f"{plan.ops} deform ops ({plan.placed} after mirrors"
           + (f", {plan.tucked} vertices tucked" if plan.tucked else "") + ")"] if plan.ops else []) + \
        ([f"{variant.mesh.gltf[0]}'s edit"] if edit else [])
    others = sorted(s for s, row in rows.items() if s not in (species, PLAYER)
                    and (row["body"] or "").casefold() == plan.body.casefold())
    grown = (f"{plan.added} vertices added by its subdivide ops ({plan.vertices} now, {len(plan.mesh.triangles)} "
             f"triangles), " if plan.added else "")
    return (f"its mesh: {grown}{len(plan.positions)} of {plan.body}'s {plan.vertices} vertices moved by {' and '.join(by)}, "
            f"up to {plan.largest:.3f} model units, normals recomputed on {len(plan.normals)}, "
            f"{plan.turned} triangles turned over (W24)"
            + (f"; {', '.join(others)} wear the same body: their NPCs "
               + ("keep vanilla's mesh (P2)" if restored else "change too") if others else ""))


def _his_words(variant, worn, columns: list[str], picks: list[str], recipe_picks: dict, reshaped, painted: list,
               styled: int, stride: dict, looped, rows: list, engine) -> list[str]:
    """The log words of a recipe's layers on garret4's own build (Step
    2.206) before its shims' (:func:`_his_recipe`)."""
    from azurkit.tools.characters import _player_variants as variants

    return (([f"its {', '.join(worn.markers)} grown"] if worn.markers else [])
            + ([f"its clips {', '.join(sorted(worn.clips))} under characters/{PLAYER}/{variants.VARIANT_DIR} (W22)"]
               if worn.clips else [])
            + ([f"{len(recipe_picks)} columns playing its picks at his Rates (W3: "
                + ", ".join(f"{columns[i]} {picks[i]}" for i in sorted(recipe_picks)) + ")"] if recipe_picks else [])
            + (["his hits through walls (his hitsThroughWalls 1.0, W22)"] if worn.through_walls else [])
            + ([_reshaped_line(reshaped, variant, _species(engine), PLAYER)] if reshaped is not None else [])
            + ([f"his arms {variant.arms:g} deg wider in {styled} clips, all but its v/ ones (W28)"]
               if variant.arms else [f"its poses in {styled} clips (W28)"] if variant.poses or variant.arm_clips
               else [])
            + ([f"its textures (W30): {'; '.join(painted)}"] if painted else [])
            + ([_idles_line(variant)] if variant.idles else [])
            + ([_slots_line(variant, stride)] if variant.slots else [])
            + ([f"its victories end at a push of the stick {variant.victory_cancel:g} s in, else play whole (X46)"]
               if variant.victory_cancel is not None else [])
            + ([f"B's hand spin chaining planted from {looped[0]:.4f} to {looped[1]:.4f} of its clip (W37)"]
               if looped is not None else [])
            + ([f"{len(rows)} config rows for its projectile (W30)"] if rows else []))


def _garret4_recipe(game, variant, sound_files, options: dict) -> list[str] | None:
    """A recipe on garret4's own body (Step 2.170c, D748; since Step
    2.206, D813, every field his body can take:
    :data:`~azurik_mod.patches._player_variants.GARRET4_REFUSED`): with
    his staff or a prop on his staff chain, his own build at its options
    (scale, attack numbers, weapon) with its layers made on it
    (:func:`_apply_garret4`, :class:`_Recipe`); under a style on his rig
    (bare hands, Balthazar's magic: Step 2.161d) his own build alone when
    it asks for nothing but its options and colours (a ``drain`` is the
    style's, X37), else ``None``: the
    swap path dresses it (``apply_player_model``, its colours in his rows
    in place there).  A recipe with no layer gets W38 in place after his
    build (no copy and no X47: only he wears his body) and the variant's
    status.  :class:`ValueError` names a name a species has, a balance or
    reach-to-ground his own attacks can't take and what his body can't
    build; the build writes no ISO (D35)."""
    from azurkit.tools.characters import _player_variants as variants

    who = f"--player-character {variant.name!r}"
    engine = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("critters_engine")
    characters = game.stored("characters.xbr")
    body = read_body(characters, PLAYER)
    columns = XbrDocument.from_bytes(game.stored("config.xbr")).keyed_section("attacks_anims").col_names()
    why = variants.refusal(variant, _species(engine), columns, body)
    if why:
        raise ValueError(f"{who}: {why}")
    drop = variants.variant_sounds(variant, sound_files)   # its WAVs and the drop-ins, read before any write
    try:
        lo = loadout(characters, body, options["mode"], False, variant, options["weapon"])
    except ValueError as exc:
        raise ValueError(f"{who}: {exc}") from None
    worn = lo.recipe if lo.recipe is not None else variant
    layered = _layered(variant, worn, drop)
    if lo.kit is not None and (layered or worn.drain != "nearest"):   # a style's drain takes it (X37)
        return None
    o = options
    if lo.kit is None:
        for key, on in (("balance", worn.balance), ("ground", worn.ground)):
            if on and not lo.picked:
                raise ValueError(f"{who}: attacks.{key} true: garret4 plays his own attacks with his staff, "
                                 + ("the ones the balance weighs a swapped body's against" if key == "balance" else
                                    "and his hit boxes are his own") + "; leave it out, or give it a weapon")
        log = _apply_garret4(game, o["model_scale"], o["attack_reach"], o["attack_damage"], o["attack_speed"],
                             o["attack_balance"], o["attack_ground"], o["logic"], lo, o["mode"],
                             _Recipe(variant, worn, drop, o["jiggle_strength"], o["jiggle_stiffness"],
                                     o["springs_out"], o["plans"], o["ram"]), chain=o["chain"])
        if not log[0].endswith("; nothing written"):
            return log
    else:   # the style it wears, the recipe's or the one picked over it
        log = apply_player_model(game, PLAYER, **{**options, "weapon": lo.name})
    try:
        grown, _, coloured = write_colours(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), PLAYER,
                                           located(variant.colours, variants.colour_folder(variant)), in_place=True)
    except ValueError as exc:
        raise ValueError(f"{who}: {exc}") from None
    game["characters.xbr"] = bytearray(grown)
    colour, why = variants.status(variant, o["model_scale"], o["attack_reach"], o["attack_damage"],
                                  o["attack_speed"])
    return [*(line for line in log if not line.startswith("  Player model status:")
              and not line.endswith("; nothing written")),
            f"  Player model: {variant.name}, a variant of {PLAYER} (recipe {variant.sha}, {variant.source}): "
            + (f"his colours in his own body's rows, in place (W38, no copy: only he wears it): "
               f"{'; '.join(coloured) or 'none'}" if variant.colours else "its options on his own build"),
            f"  Player model status: {colour} ({why})"]


def apply_player_model(game, species: str, *, mode: str = DEFAULT_MODE, size: str = DEFAULT_SIZE,
                       model_scale: float = 1.0, attack_reach: float = 1.0, attack_ground: bool | None = None,
                       attack_balance: bool | None = None, attack_damage: float = 1.0,
                       attack_speed: float = 1.0, missing_anims: str | None = None,
                       sounds: str = "own", logic: AttackLogic | None = None, variant=None,
                       sound_files: str | Path | None = None, jiggle_strength: float = 1.0,
                       jiggle_stiffness: float = 1.0, springs_out: dict | None = None,
                       weapon: str | None = None, ram: int | None = None, plans: list | None = None,
                       player_only: bool = True, chain: str = DEFAULT_CHAIN) -> list[str]:
    """Dress the player in ``species``' body (W1-W7 above, and the shims
    it needs) in ``game``'s staged files (an
    :class:`~azurik_mod.patching.xbr_staging.IsoStaging`) in gameplay
    ``mode`` (:data:`MODES`) at ``size`` (:data:`SIZES`: ``garret4``
    stands it at garret4's height), drawn ``model_scale`` times that size
    (any finite number, D23; Step 2.98, D279), and return the build-log
    lines: what it wrote and the model's status.  An ``attack_reach`` other than 1.0
    (any finite number, D23), ``attack_ground`` or the balance's reach
    bump installs X13: the player's hit boxes reach that many times as
    far, and with ``attack_ground`` every attack's box is filled to the
    feet, the facing line and the floor (D222, D223, D347; Step 2.132).  ``attack_balance`` (D223, D228) weighs each
    attack's Damage multiplier against garret4's (W14,
    :func:`weigh_attacks`); ``attack_damage`` multiplies every attack's
    Damage multiplier and ``attack_speed`` every attack's Rate but the
    roll's, on top (any finite number, D23).  ``attack_ground`` and
    ``attack_balance`` left ``None`` take the mode's
    (:data:`ATTACK_DEFAULTS`).  ``missing_anims`` is X11's rule for the
    base clips the body lacks ("garret4" or "own",
    :data:`~azurik_mod.patches._player_slots.ANIMS`; ``None``, the
    mode's, :data:`MODE_ANIMS`; a body with no clips, garret4's).  ``sounds``
    (:data:`~azurik_mod.patches._player_sounds.SOUND_MODES`): ``"own"``
    gives the player the model's own sounds where it has them (X14,
    D231), ``"garret4"`` keeps Garret's.  ``logic``, when given, receives
    what the randomizer's logic reads of the build's attacks
    (:class:`AttackLogic`, Step 2.73).  ``species`` garret4 is his own
    body drawn ``model_scale`` times his size, the attack sliders on his
    own table (:func:`_apply_garret4`, Step 2.123), the vanilla player at
    x1 with every slider at 1.0.  ``variant`` (a
    :class:`~azurik_mod.patches._player_variants.Variant` whose base is
    ``species``; Step 2.137, D359) builds that recipe: its columns play its
    clips (W22, generated after B and W17 on the body its markers grow,
    under ``characters/<body>/v/``), X10 only with its ``rotate``, X21's
    search no farther than its farthest melee box, X33 for its ``carry``
    columns; the caller passes its numbers (``_player_variants.options``).
    Its ``voice``, ``sfx`` and ``wavs`` (Step 2.141, 2.144; D328, D384,
    D386) bind through
    :func:`~azurik_mod.patches._player_sounds.variant_roles` (X14, W9,
    X15), its sounds made at build time or read from its WAVs and
    appended to ``fx.xbr`` (with their ``index.xbr`` records) after every
    other write; ``sound_files`` (``--player-variant-sounds``) is a
    folder of WAVs laid over them by role
    (``_player_variants.variant_sounds``).  Either takes a base with no
    sounds of its own.  Under another weapon (Step 2.161g, D585) its
    ``sfx`` and their WAVs go with its moveset.  A variant whose jiggle bones have a real-time
    ``spring`` gets X41 (Step 2.156; D444, D445): ``jiggle_strength``
    times every offset they show (0 installs nothing) and
    ``jiggle_stiffness`` times their springs' stiffness (any finite
    numbers, D23); so does a build wearing a body ``chains.json`` lists
    with no jiggle of its own, its hair's rows (Step 2.169f:
    ``_player_variants.chain_springs``); a body without spring rows takes
    both and writes nothing.  ``springs_out``, when given, receives the rows, W29's
    placed bones and the body's inverse binds, the clips' playback rates,
    the slots' clips and the stride cells, the body, the built
    ``characters.xbr`` and the drawn scale (``azurik-mod model jiggle``'s
    preview).  ``weapon`` (Step 2.161b; D492-D495) is the weapon the body
    wears (:func:`~azurik_mod.patches._player_weapons.loadout`: a name of
    ``weapons.json``, ``own`` or ``default``; ``None``, a variant's
    recipe's, else the body's default, today's build): W31's carriers,
    the style's clips, W32's prop mesh, W33 and X3's rows grown to the
    prop's tip.  ``ram`` (``--ram``, Step 2.162i, D576) is the machine's
    MiB the build is for, 64, 128 or 256 (:data:`~azurik_mod.assets.model_inspect.RAMS`;
    ``None``, :data:`~azurik_mod.assets.model_inspect.DEFAULT_RAM`, 128
    since D588): the own runs' size lines it is weighed against
    (:func:`_load_budget`).  ``chain`` (Step 4.3, D1045;
    :data:`~azurkit.tools.characters.CHAINS`): "hit", the combo's next
    attack only onto the target the last one stunned (rows 28-31's gate
    kept, as garret4's); "any", on any press in its window
    (:func:`lift_chain_gates`), on any body, garret4's own too.
    ``plans``, when given, receives W24's plan (the variant's
    :class:`~azurik_mod.assets.mesh_edit.MeshPlan`, the one the build
    writes; none for a recipe with no ``mesh``: ``azurik-mod model dress``).
    ``player_only`` (P2, Step 2.203, D543): a picked prop (W31-W33) or a
    recipe's mesh (:func:`remeshes`) on a body some level places a critter
    wearing goes into W38's copy, which X47 binds for the player alone,
    and the body's own entries back to vanilla's for its NPCs
    (:func:`~azurik_mod.assets.paint.npc_body`); false (``model dress``'s
    preview build) leaves them in the body, as its readers read it.
    :class:`ValueError` names why
    the species can't be used, an unknown or retired mode
    (:data:`RETIRED_MODES`) or size or a slider that isn't finite, a
    recipe the body can't build, and the build writes no ISO (D35)."""
    from azurkit.tools.characters.model_inspect import DEFAULT_RAM, RAMS

    ram = DEFAULT_RAM if ram is None else ram
    if ram not in RAMS:
        raise ValueError(f"--ram {ram!r}: not one of {', '.join(map(str, RAMS))} (MiB)")
    model_scale = finite_slider_value("--player-character-scale", model_scale)
    attack_reach = finite_slider_value("--player-attack-reach", attack_reach)
    attack_damage = finite_slider_value("--player-attack-damage", attack_damage)
    attack_speed = finite_slider_value("--player-attack-speed", attack_speed)
    jiggle_strength = finite_slider_value("--player-jiggle-strength", jiggle_strength)
    jiggle_stiffness = finite_slider_value("--player-jiggle-stiffness", jiggle_stiffness)
    if sounds not in SOUND_MODES:
        raise ValueError(f"--player-character-sounds {sounds!r}: not one of {', '.join(SOUND_MODES)}")
    if mode in RETIRED_MODES:
        raise ValueError(f"--player-character-mode {RETIRED_MODES[mode]}")
    if mode not in MODES:
        raise ValueError(f"--player-character-mode {mode!r}: not one of {', '.join(MODES)}")
    if size not in SIZES:
        raise ValueError(f"--player-character-size {size!r}: not one of {', '.join(SIZES)}")
    if chain not in CHAINS:
        raise ValueError(f"character: chain {chain!r} is not one of {', '.join(map(repr, CHAINS))}")
    check_player_model(game, species)
    if sound_files is not None and variant is None:
        raise ValueError(f"--player-variant-sounds {sound_files}: it fills a variant's sounds, and "
                         f"--player-character {species!r} is a species")
    drop = {}
    from azurkit.tools.characters import _player_variants as variants
    if variant is not None and species == PLAYER:   # Step 2.170c (D748), Step 2.206 (D813): his own build and
        # the recipe's layers on it; under a style on his rig with layers, the swap path below
        made = _garret4_recipe(game, variant, sound_files, dict(
            mode=mode, size=size, model_scale=model_scale, attack_reach=attack_reach, attack_ground=attack_ground,
            attack_balance=attack_balance, attack_damage=attack_damage, attack_speed=attack_speed,
            missing_anims=missing_anims, sounds=sounds, logic=logic, jiggle_strength=jiggle_strength,
            jiggle_stiffness=jiggle_stiffness, springs_out=springs_out, weapon=weapon, ram=ram, plans=plans,
            chain=chain))
        if made is not None:
            return made
    if variant is not None:
        drop = variants.variant_sounds(variant, sound_files)   # its WAVs and the drop-ins, read before any write
    if species == PLAYER:   # his own body (Step 2.123), before the mode's attack defaults
        characters = game.stored("characters.xbr")
        try:
            lo = loadout(characters, read_body(characters, PLAYER), mode, False, variant, weapon)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
        if lo.kit is None:   # his staff, or (Step 2.161d) a prop on his staff chain: his own attacks
            return _apply_garret4(game, model_scale, attack_reach, attack_damage, attack_speed, attack_balance,
                                  attack_ground, logic, lo, mode, chain=chain)
        # Step 2.161d: a style baked onto his own rig (bare hands, Balthazar's magic), dressed below as a
        # swapped body's attacks, the parts of his body his own build's (`himself` in _dress and below); the
        # balance and the reach-to-ground the mode's, as on every body swinging a style (D222, D223, D225)
    balance, ground = ATTACK_DEFAULTS[mode]
    balance = balance if attack_balance is None else attack_balance
    asked = (attack_balance, attack_ground)   # Step 2.161g: a moveset weapon's rules where none is asked for
    attack_ground = ground if attack_ground is None else attack_ground
    colour, why = (mode_status(species, mode, size, model_scale) if variant is None else
                   variants.status(variant, model_scale, attack_reach, attack_damage, attack_speed))
    _progress.note("the dress, 1 of 5")   # its serial steps, counted for a call that notes them (sdk.match)
    d = _dress(game, species, mode, missing_anims, size, model_scale, variant, weapon)
    if plans is not None and d.reshaped is not None:
        plans.append(d.reshaped)
    doc, engine, mine, theirs, characters, body, garret4 = d.doc, d.engine, d.mine, d.theirs, d.characters, d.body, d.garret4
    missing_anims, baked, fills, victory, anims, columns, cells = d.missing_anims, d.baked, d.fills, d.victory, d.anims, d.columns, d.cells
    clips, picks, copies, plan, timers, quiets = d.clips, d.picks, d.copies, d.placed, d.timers, d.quiets
    recipe_picks, rows, reshaped, worn, swim, borrowed, surfaced, styled = (
        d.recipe_picks, d.rows, d.reshaped, d.worn, d.swim, d.borrowed, d.surfaced, d.styled)
    rigged, peaks, style, lo, painted = d.rigged, {}, d.style, d.loadout, d.painted
    himself = species == PLAYER   # Step 2.161d: his own rig wearing a style; his body's parts stay his build's
    if lo.lent and variant is None:   # Step 2.161g (D592): a moveset brings its recipe's sliders (booblord spin's
        # damage 0.6, balance off, ground on), a variant's its options' (_player_variants.options)
        m = lo.recipe
        attack_reach, attack_damage, attack_speed = attack_reach * m.reach, attack_damage * m.damage, attack_speed * m.speed
        balance = balance if asked[0] is not None or m.balance is None else m.balance
        attack_ground = attack_ground if asked[1] is not None or m.ground is None else m.ground
    w23 = worn is not None and worn.source == "overlay"   # W23's own-build overlay (Step 2.140), no variant's recipe
    colour, why = weapon_grade(variant.name if variant is not None else species, mode, lo, weapon_seen(   # D242
        size, model_scale, worn if variant is not None else None,   # a variant's at its worn moveset's sliders
        (attack_reach, attack_damage, attack_speed)), (colour, why)) or (colour, why)   # D810: no better than its own
    reaching = lo.reaching   # W26 (D339): garret4's borrowed rows grown to the prop's tip
    grown = lo if reaching or lo.carry == FLOAT else None   # a floating prop's timers too (Step 2.161e)
    sized, scale = body_scale(characters, body, theirs, mode, size)
    rolled = source_clip(body, garret4, picks[columns.index(ROLL)]) if picks else None
    roll_shim = rolled is not None and not moves_root(characters, rolled[0].name, rolled[1])
    vanilla_anims = XbrDocument.from_bytes(game.stored("config.xbr")).keyed_section("attacks_anims")
    banded: list[str] = []
    short: list[str] = []
    factors: list[float | None] = []
    entries: list[list[float | None]] = []
    bump = 0
    lift: tuple[float, bool] | None = None   # W14's factor on every B, and whether slow (D350; else D389)
    combo: Combo | None = None   # the combo W14 times, which D358's match reads (Step 2.165b)
    carry: list[tuple[float, list[float]]] | None = None
    chains: list[tuple[float, float]] | None = None
    heavy = turned = 0
    chained: list[str] = []
    sped: list[str] = []   # W14's basics chaining inside the stun at the speed slider (AZ-568)
    his_time = 0   # the columns W5 plays in garret4's time with his windows (garret4's exact), which AZ-568 reads
    stride: dict[str, float] = {}
    timed = {i: length for i, (_, length) in fills.items() if length > 0}
    borrow_hooks = needed_hooks(timed, (timers or bool(borrowed)) and not d.ahead)
    _progress.note("the dress, 2 of 5")   # the attacks, the reach and the stride
    try:
        # W1, W2 (garret4's exact: garret4's scale and bounds, D131; sized,
        # garret4's height in any mode, Step 2.68), times the model scale
        # (Step 2.98, D279): ``drawn`` is the scale every check below
        # judges the body at, as the game draws it
        if not himself:
            point_keyed_string(engine, PLAYER, "body", species, "body")
        size_scaled = 1.0 if scale is None else scale
        drawn = drawn_scale(sized, mode, theirs["scale"], model_scale)
        if model_scale != 1.0:
            scale = drawn
        if scale is not None:
            set_keyed_double(engine, PLAYER, "scale", scale, fill_empty=True)
        # its own bound at that scale (not garret4's exact), garret4's grown with the model scale,
        # never under garret4's own
        bound = max((theirs["boundRadius"] or 0.0) * drawn if mode != "garret4" else 0.0,
                    (mine["boundRadius"] or 0.0) * model_scale)
        if bound > (mine["boundRadius"] or 0.0):
            set_keyed_double(engine, PLAYER, "boundRadius", bound)
        # W16 (Step 2.75d, AZ-450): the damage its body's own field deals,
        # garret4 takes as the species does (tesla_tree: no tesla damage)
        hurt = doc.keyed_section("critters_damage")
        fielded: dict[str, float] = {}
        for kind in sorted(field_damage(characters, theirs["body"], game.stored("config.xbr"))):
            own = _doubles(hurt, species, (kind,))[kind]
            if own is not None:
                set_keyed_double(hurt, PLAYER, kind, own, fill_empty=True)
                fielded[kind] = own
        write_anims(anims, plan)   # W3
        # X3's columns (installed below; :func:`x3_mask`), own mode's
        # reach test among them, its X10 ring keeping the clips that can
        # hit (Step 2.69); no X10 in garret4's exact, whose columns each
        # play one clip in garret4's time, X3's windows being fractions of
        # it (Step 2.68)
        # X36's attack sets (Step 2.135, D325): WHITE cycles them in own body; with two or more X10's
        # ring would rotate whatever clip a set plays, so it stays off unless a recipe asks for it
        sets = attack_sets(columns, picks) if mode == "own" else []
        rotate = (rotation(columns, picks, body)
                  if picks and mode != "garret4" and (worn.rotate if worn is not None else len(sets) < 2) else None)
        if mode == "own" and rotate:
            rotate = hitting_ring(characters, body, picks, drawn, rotate)
        missed = (reach_misses(characters, body, columns, picks, drawn, rotate)
                  if mode == "own" and picks else 0)
        x3 = x3_mask(mode, columns, picks, body, missed)
        # Step 2.159b (D473, D474): the style's throw column swings no box: X42 throws from its hand
        throwing = style is not None and style.throw is not None and style.dir + style.throw.clip in picks
        tossed = sum(1 << i for i, p in enumerate(picks) if throwing and p == style.dir + style.throw.clip)
        x3 &= ~tossed
        # Step 2.167b (D538's E2): an effects row's projectile, X42 throwing it from the columns it names on top
        # of their own swing; one debug a build, so the kit's throw beside it is refused by name
        shot = projectile_row(worn, lo, variant.name if variant is not None else species)
        if shot is not None and throwing:
            raise ValueError(f"--player-character {variant.name if variant is not None else species!r}: its "
                             f"{shot.template.name} row and the bare-hands kit's {style.throw.kind} throw: X42 "
                             f"throws one species a build ({throws.SPECIES}, W30): drop the row or name a weapon")
        marker = bool(x3)
        # Step 2.159a: X3's window the style's; its box its own (Step 2.195, D763: a kit's at the limb it strikes
        # with; Step 2.195b, D767: Balthazar's his own blast's and beam's), X3 anchored at the feet
        style_hits = style_windows(style, picks, characters, body, drawn) if style is not None else {}
        boxed = bool(style_hits)
        # W5: garret4's exact, every move in garret4's time (D131); own
        # body, the roll in garret4's time, an attack over before its
        # window can hit in garret4's time too (AZ-494), and the wind-up
        # band (Q304); a recipe's Blender clip at the rate it gives, first
        # (Step 2.158: here only, so W14's speed and W19's chain point read it)
        if picks:
            for i, (cell, pick) in enumerate(zip(cells, picks)):
                given = variants.clip_rate(worn, columns[i]) if worn is not None else None
                if given is None and style is not None and style.rate is not None and pick.startswith(style.dir):
                    # Step 2.159a: the style's Rate, its move the whole clip (rate None: each column's own)
                    given = style.rate
                    for row, end in (("Move start", "Anim start"), ("Move end2", "Anim end")):
                        now, edge = anims.find_cell(columns[i], row, i), anims.find_cell(columns[i], end, i)
                        if now.type_code == 1 and edge.type_code == 1 and now.double_value != edge.double_value:
                            set_keyed_double(anims, columns[i], row, edge.double_value, col=i)   # down's 0.1
                if given is not None:
                    set_keyed_double(anims, columns[i], "Rate", given, col=i)
                    continue
                rate = anims.find_cell(columns[i], "Rate", i).double_value
                owner, clip = source_clip(body, garret4, pick)
                his = standard_rate(rate, owner.length(clip), garret4.length(cell.string_value))
                if mode == "garret4" or columns[i] == ROLL or borrowed >> i & 1:   # garret4's own: his Rate
                    new = his
                    his_time |= (mode == "garret4") << i
                elif x3 >> i & 1 or clip in owner.damage_clips:
                    window = move_window(anims, i)
                    hits = style_hits.get(pick) if x3 >> i & 1 else damage_windows(characters, owner.name, clip, drawn)
                    move, at_his = (attack_move(r, owner.length(clip), window, hits) for r in (rate, his))
                    if move is not None and move.hits == 0 and at_his is not None and at_his.hits:
                        new = his
                        short.append(columns[i])
                    else:
                        late = windup(rate, owner.length(clip), window, hits)
                        if late <= WINDUP_MAX:
                            continue
                        new = rate * late / WINDUP_MAX * (1 + RATE_MARGIN)
                        banded.append(columns[i])
                else:
                    continue
                set_keyed_double(anims, columns[i], "Rate", new, col=i)
        # X3's anchor outside garret4's exact: the action point if its box can hit there (Step 2.70b), and how
        # far its box reaches there, before W14, which weighs an X3 column at it (AZ-415); Step 2.161e: a rigid
        # prop's tip (its reach ahead W14's bump grows, below)
        point = action_point(characters, body, picks)
        tipped = (tip_plan(characters, body, lo, anims, columns, picks, drawn, rotate, attack_reach)
                  if lo.tip else None)
        x3_bone, x3_point, x3_offset = (x3_anchor(characters, body, point, anims, picks, x3, drawn, rotate,
                                                  x3_side(model_scale))
                                        if marker and not timers and not borrowed and mode != "garret4"
                                        and tipped is None and not boxed else (-1, (0.0,) * 3, GARRET4_BOX))
        # Step 2.195: a style's boxes stand where its clips strike (X3 anchored at the feet), each X3 column's reach
        # its own box's, garret4's where he holds it in any other
        kit_far = {c: (max(w.forward for w in style_hits[p]), max(w.reach for w in style_hits[p]))
                   if p in style_hits else (GARRET4_FORWARD, GARRET4_REACH)
                   for i, (c, p) in enumerate(zip(columns, picks)) if boxed and x3 >> i & 1 and c != ROLL}
        x3_far = (tipped.corner if tipped is not None   # Step 2.161e: a rigid prop's tip
                  else max(r for _, r in kit_far.values()) if kit_far   # Step 2.195: a style's own boxes
                  else GARRET4_REACH if x3_bone >= 0   # a hand, which no build measures (D237)
                  else x3_reach(x3_point, x3_offset, drawn))   # where X3 put its box: his feet, a point
        # garret4's box where he holds it (a hand, his feet) weighs as his attack_1's own box
        weighed = None if tipped is None and (x3_bone >= 0 or x3_offset == GARRET4_BOX) else x3_far
        # W14 (Step 2.69): the attack balance (D223, D228) and the damage
        # and speed sliders on top of it, every attack but the roll; on a
        # body with no clips, whose timers play garret4's, the sliders alone
        # (Step 2.123, AZ-565: the balance weighs a body's own clips)
        # X13's fill (installed below; Step 2.132, AZ-605), which W19's contact and W14's slow
        # test read (AZ-534, AZ-614)
        mask = fill_mask(columns) if attack_ground and (picks or timers) else 0
        if worn is not None:   # a recipe's own clips keep their boxes as keyed (Step 2.137: the sweep's turning bar)
            mask &= ~variants.authored(worn, columns)
        mask &= ~tossed
        weigh = balance and bool(picks)
        if logic is not None and not weigh and picks and mode == "own":   # D358's match times it unweighed
            combo = weigh_attacks(characters, body, drawn, vanilla_anims, anims, picks, x3, rotate, False,
                                  attack_reach, mask, borrowed, style_hits, grown, balance=False, x3_far=weighed,
                                  model_scale=model_scale)[4]
        if (picks or timers) and (weigh or attack_damage != 1.0 or attack_speed != 1.0):
            if weigh:
                factors, bump, entries, lift, combo = weigh_attacks(characters, body, drawn, vanilla_anims,
                                                                    anims, picks, x3, rotate, mode == "garret4",
                                                                    attack_reach, mask, borrowed, style_hits, grown,
                                                                    x3_far=weighed, model_scale=model_scale)
                if tipped is not None and bump:
                    tipped = tip_plan(characters, body, lo, anims, columns, picks, drawn, rotate, attack_reach, bump)
                if w23:   # W23: a thrown box passes a target once (about 4
                    # ticks), not the balance's held target, so its columns keep garret4's multiplier
                    thrown = variants.authored(worn, columns)
                    factors = [None if thrown >> i & 1 else b for i, b in enumerate(factors)]
                factors = [None if tossed >> i & 1 else b for i, b in enumerate(factors)]   # the throw: his x the slider
            base: list[float] = []   # garret4's multiplier per column (an empty cell 1.0)
            rates: list[float] = []
            for i, col in enumerate(columns):
                cell = vanilla_anims.find_cell(col, MULTIPLIER, i)
                base.append(cell.double_value if cell is not None and cell.type_code == 1 else 1.0)
                rates.append(anims.find_cell(col, "Rate", i).double_value * attack_speed)
                if col == ROLL:
                    continue
                if weigh or attack_damage != 1.0:
                    b = factors[i] if weigh and factors[i] is not None else 1.0
                    set_keyed_double(anims, col, MULTIPLIER, base[i] * (b * attack_damage), col=i,
                                     fill_empty=True)
                if attack_speed != 1.0:
                    set_keyed_double(anims, col, "Rate", rates[i], col=i)
                    if (his_time >> i & 1 or timers and not picks) and col in CHAINED:   # AZ-568: garret4's
                        # timing and windows (Skin only; a clipless body's timers his clips), his chain in the stun
                        his = vanilla_anims.find_cell(col, "Anim", i).string_value
                        end1 = speed_chain(vanilla_anims, i, garret4.length(his), damage_windows(characters, PLAYER, his),
                                           attack_speed, follow_hit(vanilla_anims, i, lambda j: (
                                               garret4.length(c := vanilla_anims.find_cell(
                                                   vanilla_anims.col_names()[j], "Anim", j).string_value),
                                               damage_windows(characters, PLAYER, c))))
                        if end1 is not None:
                            set_keyed_double(anims, col, "Move end1", end1, col=i)
                            sped.append(col)
            if weigh and rotate:   # X10's ring carries each clip's own (installed below)
                carry = [(rates[h], [base[c] * ((1.0 if b is None else b) * attack_damage)
                                     if rotate[1] >> c & 1 else 0.0 for c, b in enumerate(row)])
                         for h, row in zip(rotate[0], entries)]
            # X18 (Step 2.104, AZ-525): a light column garret4's hit stuns in written at 1.0 or more
            # (the balance, the damage slider, X10's ring) no longer stuns, unless X18 keeps it
            light = light_columns(vanilla_anims)
            written = [anims.find_cell(col, MULTIPLIER, i) for i, col in enumerate(columns)]
            heavy = sum(1 << i for i, cell in enumerate(written) if light >> i & 1 and cell is not None
                        and cell.type_code == 1 and cell.double_value >= LIGHT)
            heavy |= sum(1 << c for _, row in carry or () for c, m in enumerate(row)
                         if light >> c & 1 and m >= LIGHT)
        # W19 (Step 2.104, AZ-523): own body's ring entry chains at its own clip's point in a
        # basic it turns, at the Rate the swing plays, with the balance or without it
        # (basic1-3 each play the whole clip); from its box's contact with the target ahead
        # where that comes late (Step 2.105, AZ-495), its reach and its fill X13's in the
        # column (Step 2.106, AZ-534; Step 2.132); and in any other column it turns where some entry's
        # kept Move end1 chains before that entry touches the target (Step 2.106, AZ-495)

        def reach_of(i: int) -> float:
            return attack_reach * (REACH_BUMP if bump >> i & 1 else 1.0)

        read: dict[tuple, tuple[tuple[DamageWindow, ...] | None, float | None]] = {}

        def reads(i: int, owner: Body, clip: str) -> tuple[tuple[DamageWindow, ...] | None, float | None]:
            """Column ``i``'s windows (``None``, X3's; a style's clip's, its window) and contact
            playing ``owner``'s ``clip``."""
            if x3 >> i & 1:
                return style_hits.get(clip), None
            key = (owner.name, clip, move_window(anims, i), reach_of(i), bool(mask >> i & 1))
            if key not in read:
                read[key] = (damage_windows(characters, owner.name, clip, drawn),
                             contact(characters, owner.name, clip, drawn, owner.length(clip), key[2], key[3], key[4]))
            return read[key]
        if mode == "own" and rotate:
            ring = [source_clip(body, garret4, picks[h]) for h in rotate[0]]
            turned = sum(1 << i for i, col in enumerate(columns) if rotate[1] >> i & 1 and col != ROLL and (
                col in CHAINED or any(chains_early(anims, i, owner.length(clip), *reads(i, owner, clip))
                                      for owner, clip in ring)))
            first = next((i for i in range(len(columns)) if turned >> i & 1), None)
            if first is not None:
                chains = [chain_terms(owner.length(clip), move_window(anims, first), *reads(first, owner, clip))
                          or (0.0, 0.0) for owner, clip in ring]
        # W19 (Step 2.104, AZ-496): own body, each basic's chain point
        # 0.2 s after its first damage tick, where a light hit's stun holds;
        # any other column's only where its own chains before its move
        # touches the target ahead (Step 2.106, AZ-495)
        # (Step 2.135) the columns a set plays in basic1-3 chain there as the basics do
        set_basics = {columns[c] for cols in sets[1:] for c in cols[:3]}
        if mode == "own" and picks:
            for i, col in enumerate(columns):
                if col == ROLL or (rotate and rotate[1] >> i & 1) or borrowed >> i & 1:   # his Move end1 stands
                    continue
                owner, clip = source_clip(body, garret4, picks[i])
                length, (hits, met) = owner.length(clip), reads(i, owner, clip)
                if col not in CHAINED and col not in set_basics and not chains_early(anims, i, length, hits, met):
                    continue
                end1 = chain_point(anims, i, length, hits, met)
                if end1 is not None:
                    set_keyed_double(anims, col, "Move end1", end1, col=i)
                    chained.append(col)
        # W23's thrown columns (Step 2.145, D414): held, the next throw leaves as this one's box
        # arrives, Move end1 that fraction of the clip as 0x7E2E0 reads it (Anim start, end: 0, 1 if empty)
        thrown = variants.authored(worn, columns) if w23 else 0
        for i, col in enumerate(columns):
            if thrown >> i & 1 and worn.clips[worn.columns[col]]["generator"] == "gust":
                p = worn.clips[worn.columns[col]]
                a0, a1 = (c.double_value if (c := anims.find_cell(col, row, i)) is not None and c.type_code == 1
                          else empty for row, empty in (("Anim start", 0.0), ("Anim end", 1.0)))
                set_keyed_double(anims, col, "Move end1", a0 + p["arrive"] / p["length"] * (a1 - a0), col=i,
                                 fill_empty=True)
        toss = None
        if tossed:   # Step 2.159b: a new press throws again at its chain tick (a held A once: D566, Step 2.159d),
            # along the facing (F10), and W30's species rows
            i = tossed.bit_length() - 1
            a0, a1 = (anims.find_cell(columns[i], row, i).double_value for row in ("Anim start", "Anim end"))
            set_keyed_double(anims, columns[i], "Move end1", a0 + style.throw.chain / style.throw.ticks * (a1 - a0),
                             col=i)
            set_keyed_double(anims, columns[i], "Aim angle", 0.0, col=i, fill_empty=True)
            try:
                toss = throws.plan(style.throw, characters, body, columns, picks, style.dir, drawn,
                                   XbrDocument.from_bytes(game.stored("config.xbr")), doc,
                                   d.take[0] if d.take is not None else None, lo.grip or throws.HAND)
            except ValueError as exc:
                raise ValueError(f"--player-character {species!r}: {exc}") from None
            toss_rows = throws.write_species(doc, toss.scale)
        elif shot is not None:   # Step 2.167b: the row's projectile, released at each column clip's first hit
            try:
                timing = shot_timing(characters, body, garret4, anims, columns, picks, style_hits, drawn, shot)
                toss = throws.template_plan(shot, game.stored("characters.xbr"), columns, timing, doc, drawn,
                                            throw_bone(characters, body, lo, picks))
            except ValueError as exc:
                raise ValueError(f"--player-character {variant.name if variant is not None else species!r}: "
                                 f"{exc}") from None
            v = shot.values
            toss_rows = throws.write_species(doc, toss.scale, min(float(v["radius"]), float(v["size"]) / 2))
        loop = worn.loop() if worn is not None and mode == "own" else None
        looped = (planted_chain(anims, doc.keyed_section("attacks_transitions"), tuple(loop["plant"]),
                                float(loop["turns"]), float(loop["hold"]))
                  if loop is not None else None)   # W37 (Step 2.180, D701)
        if chain == "any":   # D1045's option (Step 2.153's D432 rule): rows 28-31's stunned-target gate lifted
            lift_chain_gates(doc)
        # what the columns play: a creature's cast in a body's k/ copies or a clipless body's g4/ timers (Step 2.204;
        # the train review's N1: its picks, the plain clips, key no cast, so X37 aimed none of its bolts)
        column_clips = cast_plays(picks, copies, clips, d.cast) if d.cast else picks
        beams = beam_columns(characters, body, columns, column_clips) if mode == "own" and column_clips else 0
        ranged = bool(beams) and ranged_finisher_columns(columns, beams)
        finish = None
        if ranged:   # W40 (Step 2.197b, D797; D804 (b)): past the blast's reach the combo ends on his beam
            ranged_finisher(doc.keyed_section("attacks_transitions"))
            f = columns.index("finish")
            owner, clip = source_clip(body, garret4, picks[f])
            try:
                finish = finish_line(reads(f, owner, clip)[0], reach_of(f))
            except ValueError as exc:
                raise ValueError(f"--player-character {species!r}: {exc}") from None
        # W7 (own body): its stride on garret4's calibration (Step 2.133, AZ-610), else the species'; a
        # variant's own gait by its planted feet (Step 2.171); X11's fill first, as the slot plays it
        if mode != "garret4" and not himself:
            data = doc.keyed_section("critters_critter_data")
            plays = {i: c for i, name in enumerate(BASE_CLIPS) for c in body.clips if c.casefold() == name} | {
                i: c for i, (c, _) in fills.items()}
            stride = stride_cells(characters, body, plays, _doubles(data, species, _STRIDE),
                                  _doubles(data, PLAYER, _STRIDE),
                                  frozenset(recipe_fills(worn.slot_clips())) if worn is not None else frozenset())
            for prop, value in stride.items():
                set_keyed_double(data, PLAYER, prop, value)
        if worn is not None and worn.through_walls:   # W22 (Step 2.140, D385): its hits skip the wall test
            set_keyed_double(doc.keyed_section("critters_critter_data"), PLAYER, "hitsThroughWalls", 1.0)
        # W4; none for a copied Axion staff (Step 2.161b, F-E): its carriers are his ends by name, so the staff
        # graphs bind them as on him, power heads and all
        fx = _load_doc_for_edit(game, "fx.xbr")
        staff = [] if lo.native else staff_scales(fx.raw)
        for at in staff:
            replace_bytes_at(fx, at, _HIDDEN, expected=_SHOWN)
        # W6 (Step 2.24f): the staff's particles come from the action
        # point (D219, Step 2.64): the hands, else a fixed point
        hands = lo.fx_ends or point.hands   # W26 (Step 2.134b, D338): at the prop's ends
        heads, euler = (None, None) if lo.native else power_shape(game, characters, body, lo, point)
        if lo.native:
            hands = lo.carriers.bones
            if lo.k != 1.0:   # Step 2.203: the staff's fx at the copy's size about its ends (W32 drew the shaft x k)
                from azurkit.tools.characters import _player_power_fx as power

                heads, euler = power.staff_shape(lo.k), Euler(bytes(game["default.xbe"]))
                power.reshape(fx, heads, euler, bound=True)
        elif hands:
            follow_hands(fx, hands, heads, euler)   # its power heads reshaped for them (Step 2.182, D707)
        else:
            at_point(fx, heads, euler)
        armor = fit_armor(fx, characters, body)   # W15 (Step 2.77b)
    except XbrStructuralError as exc:
        raise ValueError(f"--player-character {species!r}: {exc}") from None
    _progress.note("the dress, 3 of 5")   # the shims and the camera
    if roll_shim:   # X4
        try:
            install_roll_shim(game["default.xbe"])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    # Step 2.161e: X3's box at a rigid prop's tip on every attack column (Balanced), the body's own windows
    if tipped is not None:   # in place of the body's own boxes (the 2.161 design's S3, S4: exact mode, slot 2 off)
        install_damage_marker(game["default.xbe"], species, columns=tipped.columns, bone=tipped.bone,
                              offset=(0.0, 0.0, 0.0), boxes=tipped.rows)
    # X3: garret4's own box and window on every column (Step 2.68), in
    # every mode for a clipless body's timers, his clips (Step 2.75e, AZ-473), grown to a floating prop's tip
    # (Step 2.161e)
    elif timers or (mode == "garret4" and marker):
        install_damage_marker(game["default.xbe"], species, boxes=garret4_boxes(
            characters, clips, (lambda clip: held_window(characters, clip, drawn, lo)) if lo.carry == FLOAT else None))
    elif borrowed:   # garret4's own box and window on each of his attacks (Step 2.134a), a recipe's its own,
        # grown to a carried prop's tip (W26, D339)
        install_damage_marker(game["default.xbe"], species, columns=x3, boxes=garret4_boxes(
            characters, clips, (lambda clip: held_window(characters, clip, drawn, lo)) if reaching else None))
    elif marker:   # X3 (Step 2.21c): per column, at the action point (Step 2.64) if it can hit there (2.70b),
        # a style's clip's window its own (Step 2.159a)
        install_damage_marker(game["default.xbe"], species, columns=x3, bone=x3_bone, point=x3_point,
                              offset=x3_offset, side=x3_side(model_scale) if x3_bone >= 0 else 1.0,
                              boxes=x3_rows(anims, picks, body, style_hits, x3_offset) if style_hits else None)
    if body.clips and not himself:   # X7 (Step 2.21d)
        try:
            install_hit_shim(game["default.xbe"])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if fills or victory or quiets:   # X11 (Step 2.66; the victories, Step 2.121; W22's, Step 2.131)
        try:
            install_slots_shim(game["default.xbe"], fills | victory | quiets)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    fidgets = fidget_mask(variant.idle_clips()) if variant is not None else 0
    if fidgets:   # X45 (Step 2.168, D553): a fidget after a drawn wait, never one twice in a row
        try:
            install_idle_pick(game["default.xbe"], fidgets, variant.idle_wait)
        except ValueError as exc:
            raise ValueError(f"--player-character {variant.name!r} (a variant of {species}): {exc}") from None
    if variant is not None and variant.victory_cancel is not None:   # X46 (Step 2.181, D702): the stick ends it
        try:
            install_victory_cancel(game["default.xbe"], variant.victory_cancel)
        except ValueError as exc:
            raise ValueError(f"--player-character {variant.name!r} (a variant of {species}): {exc}") from None
    if borrow_hooks:   # X12 (Step 2.67)
        try:
            install_borrow_shim(game["default.xbe"], borrow_table(timed, anim_change_return(game["default.xbe"])),
                                borrow_hooks)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if d.ahead:   # X44 (Step 2.161b2, AZ-688): garret4's baked attack before the body's own of the name
        try:
            install_first_shim(game["default.xbe"])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    # X9's zipline hang at a model scale (Step 2.104), its pose's top where garret4's (Step 2.106)
    hung = (1.0 if himself and model_scale == 1.0   # Step 2.161d: his own build's, none at x1 (his top 0.99999996)
            else hang_scale(model_scale, drawn, hang_top(characters, body, fills, lo.carriers)))
    # the camera at any drawn size (Step 2.107, D280): X8's point, X19's lift, X20 and X25's rig
    shape = camera_shape(characters, body, fills, lo.carriers)
    plan = camera_plan(shape, sized, drawn, model_scale, hung * G4_HANG_GRAB)
    if surfaced and plan.x8:   # W27's swim camera where garret4's sits, at least 0.6 m over (Step 2.150, AZ-642)
        plan = replace(plan, margins=swim_margins(plan.s if plan.rig else 1.0, SURFACE_FLOOR))
    # the size its movement folds (Step 2.133): randomize-full's fold, checked
    size_s = movement_size(SizeShape(shape, sized, size_scaled, mode == "garret4"), model_scale)
    _install_size_early(game, species, body, plan, hung, drawn, swim_eye=himself and model_scale < 1.0)   # X8, X9
    if surfaced or needs_climb_offsets(body):   # X9's ladder offsets (Step 2.63b); W27's m_root is no ladder's
        try:
            install_climb_offsets(game["default.xbe"])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    rotated = 0   # X10's ring's VA, which X38 reads
    if rotate:   # X10 (Step 2.64; its ring carrying the balance, Step 2.69)
        try:
            rotated = install_rotate_shim(game["default.xbe"], *rotate, carry, chains, turned)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if attack_reach != 1.0 or mask or bump:   # X13 (Step 2.70), only when asked for
        try:
            install_attack_box_shim(game["default.xbe"], attack_reach, mask, bump)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if logic is not None:   # what the randomizer's logic reads (Step 2.73); a clipless body's X3 serves every column
        swings = tuple(c for c in IDLE_SWINGS if tipped is None or c in tipped.kept)
        logic.reach = melee_reach(   # by each box's forward extent (Step 2.137, AZ-604); a kit's, its idle swings'
            characters, body, columns, picks, drawn, x3 if picks else (1 << len(columns)) - 1,
            max((f for c, (f, _) in kit_far.items() if c in swings), default=0.0) if kit_far
            else GARRET4_FORWARD if x3_bone >= 0 else x3_forward(x3_point, x3_offset, drawn),
            rotate, clips if mode == "garret4" or timers or borrowed else None, attack_reach, bump,
            model_scale=model_scale, ahead=True, held=grown, only=swings,
            rates=[anims.find_cell(col, "Rate", i).double_value for i, col in enumerate(columns)])   # AZ-766
        if tipped is not None:   # the tip's reach alone (S3), measured; a kept column's the body's own
            logic.reach = max((r for r in (tipped.forward, logic.reach if tipped.kept else None) if r is not None),
                              default=None)
        if picks:   # the multipliers W14 and X10's ring write, garret4's x B (1.0 unweighed) x the slider
            spun = rotate[1] if carry else 0
            played = [b for i, b in enumerate(factors) if columns[i] != ROLL and not spun >> i & 1]
            played += [b for row in entries for c, b in enumerate(row) if spun >> c & 1]
            logic.damage = min((1.0 if b is None else b for b in played), default=1.0) * attack_damage
        elif timers:   # W14's damage slider alone (Step 2.123, AZ-565)
            logic.damage = attack_damage
        logic.speed = attack_speed
        logic.size = size_s
        logic.height, logic.combo = height(characters, body) * size_scaled, combo   # D358's match (Step 2.165b)
    # the clips the build's Anims play (W17's copies as their clips)
    _progress.note("the dress, 4 of 5")   # the sounds
    roles = sound_roles(game, species, dict(zip(columns, picks)) if picks else None) if sounds == "own" else None
    heard = worn if variant is not None else None   # Step 2.161g (D585): its moves' sfx go with its moveset,
    if heard is not None:   # so under another weapon (unarmed) they and their WAVs drop, its shouts the one sfx
        # there (Step 2.183, D705), and nowhere else; its voice and wavs stay
        drop = {leaf: d for leaf, d in drop.items() if d.role in heard.sfx or d.role in variants.DROP_ROLES}
    voiced = variant is not None and (variant.voice != "own" or bool(heard.sfx) or bool(drop))
    made_waves = {}
    if voiced:   # a variant's own sounds (Step 2.141; D328, D384, D386)
        if roles is None:
            raise ValueError(f"--player-variant-sounds: the variant {variant.name!r} keeps Garret's sounds "
                             "(sounds garret4), so a drop-in would play no part")
        if roles.own:
            raise ValueError(f"--player-character {variant.name!r}: its base {species} has sounds of its own "
                             f"({', '.join(roles.own)}) and X14 binds every slot from one dir, so voice, sfx and "
                             "--player-variant-sounds take a base with none")
        made_waves = variants.waves(heard, drop)
        roles = variant_roles(species, variants.sound_dir(variant), columns,
                              {col: name for name, p in heard.sfx.items() for col in p["columns"]},
                              variant.voice == "silent", frozenset(d.role for d in drop.values()) - set(heard.sfx))
    # Step 2.159a (D502): bare hands' swings whoosh, from the dir X14 binds the rest from, and their hits
    # thud (X43); a variant's sounds stay its recipe's (D384, D386)
    kit_sounds = style is not None and roles is not None and variant is None
    swung = {col for i, (col, pick) in enumerate(zip(columns, picks))
             if (pick in style_hits or tossed >> i & 1) and col != ROLL} if kit_sounds else set()
    swing = swing_waves(style) if swung else {}
    if swing:
        roles = kit_swings(roles, columns, swung, style.sounds["swing"]["name"], style.sounds["dir"])
    kit_waves = {f"{roles.sound_dir}/{leaf}": samples for leaf, samples in swing.items()}
    thud = hit_wave(style) if kit_sounds else None
    if thud is not None:
        kit_waves[thud[0]] = thud[1]
    try:
        emptied = write_sound_cells(doc, roles) if roles else {}   # W9-W11 (Step 2.72)
        if roles and roles.binds:   # X14 (Step 2.71)
            install_sounds_shim(game["default.xbe"], roles)
        if roles and roles.xbe:   # X15 (Step 2.72)
            install_xbe_sounds(game["default.xbe"], roles)
    except ValueError as exc:   # XbrStructuralError too
        raise ValueError(f"--player-character {species!r}: {exc}") from None
    if needs_wings_shim(body):   # X16 (Step 2.77)
        try:
            install_wings_shim(game["default.xbe"], armor_table(fx.raw, characters, body, bytes(game["default.xbe"])),
                               theirs["body"] if surfaced else "")
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    walls = sweeps_no_staff(characters, body) or lo.walls_off   # Step 2.161d: garret4's cut staff, still swept
    if walls:   # X17 (Step 2.75d, AZ-441)
        try:
            install_staff_walls_off(game["default.xbe"])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    windowed = bool(picks or timers) and shortens_hit_delay(attack_speed)
    if windowed:   # X31 (Step 2.126, AZ-573, D318): W14's Rates sped up, the hits' no-hit window shortened
        try:
            install_hit_delay_shim(game["default.xbe"], attack_speed)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    # X32 (Step 2.132, D333; Step 2.180, D700): a body whose NPC's hits show an element's effect (his own body's
    # plain hits his own), one that swings the bare-hands kit (Step 2.159a, D467; his too) or an effects row with a
    # hit type (Step 2.167b): its plain hits show the build's small flash, never an element power's, any mode
    hit_fx = bool((not himself and hit_fx_type(game.stored("config.xbr"), species) is not None)
                  or (style is not None and style.hit_fx) or (shot is not None and shot.template.hit is not None))
    if hit_fx:
        try:
            install_hit_fx_shim(game["default.xbe"])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if thud is not None:   # X43 (Step 2.159a, D502): bare hands' plain hits thud
        try:
            install_thud_shim(game["default.xbe"], thud[0])
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    carried = (((carry_mask(species, body, columns, picks, rotate)
                 | (variants.carried(worn, columns) if worn is not None else 0))
                & ~(variants.authored(worn, columns) if w23 else 0))   # W23's gust
               if mode == "own" else 0)   # travels in the model frame: carried, it would ride and turn with her
    held = variants.held(worn, columns) if worn is not None and mode == "own" else 0
    if carried or thrown or held:   # X33 (Step 2.132, D334, D351): a flyer's or a spin's swing, or a variant's
        # carry, moves with the stick; W23's thrown columns and a recipe's held ones chain while held, uncarried
        # (Step 2.145, D414; Step 2.153, D450); the kit's throw never (D566: one throw a press, Step 2.159d)
        try:
            install_attack_carry_shim(game["default.xbe"], carried, thrown | held)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    blasts, impact = variants.blasts(worn, columns) if worn is not None and mode == "own" else (0, 0.0)
    if blasts:   # X39 (Step 2.153, D451): an air blast's clip jumps to its impact when he lands
        try:
            install_air_blast_shim(game["default.xbe"], blasts, impact)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    lines = set_lines(picks, sets)
    if sets:   # X36 (Step 2.135; D325, D326, D352; D441): WHITE cycles the sets, direction picks none
        try:
            install_attack_sets_shim(game["default.xbe"], sets, lines)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    # X18 (Step 2.104, AZ-525), after X36, whose state it reads: a light column's hit, and (Step 4.3, D1045) a set's
    # swing standing for basic1-3, stuns whatever its multiplier, so the combo chains on a hit in every set; and X37's
    # drain's hit there (its slot, light_at), whose level 2 cleared the swing's stun (beamlord's set 2)
    unstunned = set_unstunned(columns, sets, anims, carry) if sets else 0
    drain = drain_columns(columns, picks, self_drains(characters, body)) if mode == "own" and picks else 0
    light_at = 0
    if heavy or unstunned or drain & sum(1 << c for cols in sets for c in cols[:len(CHAINED)]):
        try:
            state = (trampoline_symbol_va(game["default.xbe"], SETS_HOOKS[0], SETS_STATE, CHECKOUT,
                                          shim_source=SETS_SHIM.source_path()) if len(sets) > 1 else 0)
            install_light_hit_shim(game["default.xbe"], light_columns(vanilla_anims), state)
            light_at = (trampoline_symbol_va(game["default.xbe"], LIGHT_HIT_HOOK, LIGHT_DRAIN, CHECKOUT,
                                             shim_source=LIGHT_HIT_SHIM.source_path()) if drain else 0)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    # X21 (Step 2.105, AZ-523): own body's combo on a stunned target out to its basics' reach
    far = (search_reach(characters, body, columns, picks, drawn, tipped.columns if tipped is not None else x3, x3_far,
                        rotate, attack_reach, bump,
                        melee=variant is not None or lo.lent,   # a recipe's: its melee boxes alone (Step 2.137)
                        chained=(*CHAINED, *sorted(set_basics - set(CHAINED))),   # a set's basics too (Step 2.135)
                        model_scale=model_scale)
           if mode == "own" and picks else SEARCH_RADIUS)
    # X28 (Step 2.118, AZ-529 (b); Step 2.118c): where X22 eases a hang deeper than garret4's
    _progress.note("the dress, 5 of 5")   # the holds, the fades and the writes
    hold = (hold_plan(characters, body, fills, drawn, hung, picks[columns.index(ROLL)] if picks else None,
                      lo.carriers)
            if hang_eased(body, hung) else None)
    seek = variants.seeking(worn, columns) if worn is not None and mode == "own" else 0
    chest = CHEST[1] * body_height(characters, body) * drawn   # X37's stream's pull and sink (AZ-759, AZ-764)
    rig = (chest, len(body.bones), min((p[2] for _n, p in body.bones), default=0.0), drawn)
    caster = lo.cast or style   # AZ-769 (Step 2.197b): the beam's bolts on its target, the graph's inherit-7 locators
    graph = (variants.overlay(caster.fx) if d.magic is not None and caster is not None and caster.fx is not None
             else worn)
    records = aim_records(graph.fx if graph is not None else ()) if beams else ()
    beam_far, beam_side = [], []   # the beam's box: its far face straight ahead and its farthest side, as X13
    for i in range(len(columns)) if records else ():   # grows it
        if beams >> i & 1:
            owner, clip = source_clip(body, garret4, column_clips[i])
            grow = attack_reach * (REACH_BUMP if bump >> i & 1 else 1.0)
            for w in ((style_hits.get(column_clips[i]) or ()) if x3 >> i & 1 or not picks   # X3 serves a clipless
                      else damage_windows(characters, owner.name, clip, drawn)):          # body's every column
                beam_far.append(w.forward * grow)
                beam_side.append(max(-w.low[0], w.high[0]) * grow)
    bolts = ((beams, records, max(beam_far, default=0.0) or BEAM_REACH, max(beam_side, default=0.0) or BEAM_HALF,
              chest) if records else (0, (), 0.0, 0.0, 0.0))
    late = _install_size_late(game, species, body, plan, hung, drawn, model_scale, far, hold,
                              search=bool(drain or seek or records) or toss is not None)   # X19-X29, X25
    if drain or records:   # X37 (Step 2.135; D324, D357): the worn drain lands on its target and heals, X21's radius
        # its search's; its target alone unless the recipe or the weapon style takes every critter its box touches
        # (AZ-758, D765); and the beam's bolts reach its target (AZ-769), a cast creature's with no drain too
        every = "all" in ((worn.drain if worn is not None else None),
                          (lo.weapon.style.drain if lo.weapon is not None else None))
        try:
            install_drain_shim(game["default.xbe"], drain, trampoline_symbol_va(
                game["default.xbe"], SEARCH_HOOK, SEARCH_RADIUS_SYMBOL, CHECKOUT, shim_source=SEARCH_SHIM.source_path()),
                every, DRAIN_STREAM if drain else "", rig, bolts, light_at)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if ranged:   # W40's line (Step 2.197b, D797; Step 2.202, D804 (b)): a target past the blast's reach is long range
        try:
            install_ranged_finisher(game["default.xbe"], finish)
            install_finish_range_shim(game["default.xbe"])   # X50: met on the level (Step 2.202b, AZ-803)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if seek:   # X49 (Step 2.194b, D762): a recipe's seeking columns turn to their target at the attack's start
        try:
            install_seek_shim(game["default.xbe"], seek, trampoline_symbol_va(
                game["default.xbe"], SEARCH_HOOK, SEARCH_RADIUS_SYMBOL, CHECKOUT, shim_source=SEARCH_SHIM.source_path()))
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    # X38 (Step 2.149, D429, D430): each ranged attack's effects in their own instance; after X37 (AZ-653, Step
    # 2.153c), whose state a drain row's copy is held through
    who = variant.name if variant is not None else species
    bound: list[fx_ring.Bound] = []
    holders = []   # each row's holder: (anchor, place, grow), and its graph's bytes
    shields = bound_rows(worn, lo, who)   # Step 2.167c (D538's E3): its shield and beam rows, X38's bound keys
    if shields and worn is not None and worn.fx_ring is None:
        raise ValueError(f"--player-character {who!r}: its {shields[0].template.name} row plays on X38's ring, which "
                         "its recipe's fx_ring false turns off")
    if shields:   # each its graph of its own, characters/<body>/v/fx/fx_<template>_<k> (no NPC plays it)
        new = []
        base = len(parse_toc(game["characters.xbr"]))
        for k, e in enumerate(shields):
            t = e.template
            unknown = [c for c in e.columns if c not in columns]
            if unknown:
                raise ValueError(f"--player-character {who!r}: its {t.name} row: columns: {unknown[0]!r} is no "
                                 "attacks_anims column")
            values = dict(e.values)
            for name, param in t.params.items():   # range "auto": the columns' boxes' reach ahead (m)
                if values[name] == "auto":
                    got = melee_reach(characters, body, columns, picks, drawn,
                                      tipped.columns if tipped is not None else x3, x3_far, rotate, None,
                                      attack_reach, bump, only=e.columns, melee=False,
                                      ahead=True) if picks and mode == "own" else None
                    values[name] = got if got else param["default"]
            anchor, at, grow = bound_place(characters, body, garret4, point, anims, columns, picks, style_hits,
                                           drawn, e)
            try:
                made, b, _ = fx_ring.bound_graph(bytes(game["characters.xbr"]), game.stored("default.xbe"),
                                                 game.stored("fx.xbr"), e, fx_ring.bound_key(body.name, t.name, k),
                                                 base + len(new), marker=anchor, at=at, scale=grow, values=values)
            except ValueError as exc:
                raise ValueError(f"--player-character {who!r}: {exc}") from None
            new += made
            bound.append(replace(b, columns=tuple(columns.index(c) for c in e.columns)))
            holders.append((anchor, at, grow, sum(len(r.payload) for r in made), values))
        game["characters.xbr"] = bytearray(append_resources(bytes(game["characters.xbr"]), new))
        game["index.xbr"] = bytearray(add_index_records(
            bytes(game["index.xbr"]), [IndexRecord(r.name, "characters.xbr", r.tag) for r in new if r.name]))
    try:
        played = {i: anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns) if col != ROLL}
        ringed = (fx_ring.ring_plan(bytes(game["characters.xbr"]), game.stored("default.xbe"), body, played,
                                    [played[h] for h in rotate[0]] if rotated else None, worn.fx_ring if worn else {},
                                    drains=bool(drain), bound=tuple(bound), turns=rotate[1] if rotated else 0,
                                    own=bool(picks))
                  if bound or picks and (worn is None or worn.fx_ring is not None) else None)
        if ringed is not None and ringed.rows:
            install_fx_ring_shim(game["default.xbe"], ringed, rotated, trampoline_symbol_va(
                game["default.xbe"], DRAIN_HOOKS[0], DRAIN_STATE, CHECKOUT, shim_source=DRAIN_SHIM.source_path())
                if drain else 0)
    except ValueError as exc:
        raise ValueError(f"--player-character {species!r}: {exc}") from None
    if worn is not None and worn.fx_edits or d.magic is not None:   # X40 (Step 2.157, D446): the player plays its
        # clone, every NPC its own (Step 2.161c: W34's, Balthazar's magic)
        try:
            install_fx_default_shim(game["default.xbe"], bytes(game["characters.xbr"]), bytes(game["index.xbr"]),
                                    body.name)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
    if size_s != 1.0:   # X34 (Step 2.133; D344, D356): its pickup touch at its size
        try:
            install_touch_shim(game["default.xbe"], size_s)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: {exc}") from None
        walk = write_walk_speed(game, doc, size_s)   # beside it, its walk/run switch at its size (D422)
    if rigged is not None:   # W28's springs (Step 2.143, AZ-648): last, at the rates the written cells play each clip
        rates = playback_rates(characters, doc, body, fills | victory | quiets, picks, drawn, bool(body.clips))
        try:
            _progress.note("the springs' clips")
            grown, _, peaks = variants.restyled(d.dressed, bytes(game["characters.xbr"]), d.first, body.name,
                                                variant, rigged, rates, drawn, arms=False)
        except ValueError as exc:
            raise ValueError(f"--player-character {variant.name!r} (a variant of {species}): {exc}") from None
        game["characters.xbr"] = bytearray(grown)
    sprung: list[jiggle_rt.Row] = []
    hair = variants.chain_springs(body.name) if variant is None or variant.jiggle is None else ()
    if rigged is not None and jiggle_rt.spring_bones(variant.jiggle) or hair:   # X41 (Step 2.156; D444, D445,
        try:   # D485): the spring rows on the built body, last in the XBE (after X26, whose words it keeps); a
            # body chains.json lists, its hair's rows where the build wears no jiggle of its own (Step 2.169f)
            built = bytes(game["characters.xbr"])
            binds = inverse_binds(built, body.name)
            bones_ = Rig.read(built, body.name).bones
            parents = [b.parent for b in bones_]
            own = variant.jiggle.springs if rigged is not None else hair
            try:   # rows that don't fit the body are the catalogue's (D35), the shim's and table's failures not
                placed = (*(rigged.bones if rigged is not None else ()),
                          *jiggle_rt.spring_places([b.name for b in bones_], parents, binds, own))
                sprung = jiggle_rt.rows(placed, jiggle_rt.spring_bones(variant.jiggle) if rigged is not None else
                                        {b.role: b.spring for b in hair}, binds, jiggle_stiffness, parents)
            except ValueError as exc:
                if not hair:
                    raise
                raise ValueError(f"chains.json: {exc}") from None
            if springs_out is not None:
                if rigged is None:
                    rates = playback_rates(characters, doc, body, fills | victory | quiets, picks, drawn,
                                           bool(body.clips))
                springs_out.update(
                    rows=sprung, placed=placed, parents=parents, binds=binds, rates=rates, body=body.name,
                    characters=built,
                    drawn=drawn,
                    strength=jiggle_strength, stiffness=jiggle_stiffness,
                    slots={k: c for k, n in enumerate(BASE_CLIPS) for c in body.clips if c.casefold() == n}
                    | {k: c for k, (c, _) in (fills | victory | quiets).items()},
                    cells=_doubles(doc.keyed_section("critters_critter_data"), PLAYER,
                                   (*_STRIDE, WALK_SPEED, RUN_SPEED)))
            if jiggle_strength != 0.0:
                x26 = (tuple(trampoline_symbol_va(game["default.xbe"], STANCE_HOOK, f"_player_model_stance_{w}",
                                                  CHECKOUT, shim_source=STANCE_SHIM.source_path())
                             for w in ("held", "edge")) if "X26" in late else (0, 0))
                carried = len(lo.prop.carriers) if lo.carry in (RIGID, FLOAT) else 0   # W31's, after X41 (AZ-783)
                install_jiggle_shim(game["default.xbe"], jiggle_rt.table(sprung, len(bones_) + carried,
                                                                         jiggle_stiffness, drawn), jiggle_strength, x26)
        except ValueError as exc:
            who = (_named(species) if variant is None else
                   f"--player-character {variant.name!r} (a variant of {species})")
            raise ValueError(f"{who}: {exc}") from None
    if lo.carry in (RIGID, FLOAT):   # W31 on a creature or a token (Step 2.161e): its carriers after every measure
        try:   # of its pose (a token's one bone stays one to them); a clipless body's g4/ clips key the floating one
            grown = add_carriers(bytes(game["characters.xbr"]), body, lo)
            game["characters.xbr"] = bytearray(float_clips(grown, body, lo, drawn) if lo.carry == FLOAT else grown)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: W31: {exc}") from None
    if lo.copied:   # W32 (Step 2.161b): its prop's mesh, after W28 (whose rewrite would keep no new
        try:   # relocated field) and X41; no measure of the body reads it
            grown, propped = copy_prop(bytes(game["characters.xbr"]), body, lo)
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: W32: {exc}") from None
        game["characters.xbr"] = bytearray(grown)
    # W41 in its own clips (Step 2.207b, AZ-785): after every other write of them, a held prop over the floor
    grown, kept_up = own_lifted(bytes(game["characters.xbr"]), body.name, lo, game.stored("characters.xbr"))
    grown, faded = faded_lifted(grown, body.name, lo)   # and through its crossfades (Step 2.207c, AZ-806)
    if kept_up or faded:
        game["characters.xbr"] = bytearray(grown)
    if lo.cut:   # W33 (Step 2.161d): garret4's staff cut from his mesh, after every other write of his body
        try:
            grown, _ = cut_staff(bytes(game["characters.xbr"]), lo)
        except ValueError as exc:
            raise ValueError(f"{_named(PLAYER)}: {exc}") from None
        game["characters.xbr"] = bytearray(grown)
    laid, lods_bytes = [], 0
    if variant is not None and (variant.lods is not None or variant.mesh is not None):   # W39 (Step 2.166d): its
        try:   # LODs cut from its final LOD 0 (after W33), before W36 (which then adds none) and W38's copy
            _progress.note("the LODs")
            laid, lods_bytes = write_lods(game, engine, body.name, variant.lods,
                                          game.stored("characters.xbr") if variant.mesh is not None else None)
        except ValueError as exc:
            raise ValueError(f"--player-character {variant.name!r}: W39: {exc}") from None
    try:   # W36 (Step 2.166c): a big one-LOD body's shadow LOD, after every write of its LOD 0 (W32's prop in it)
        _progress.note("the shadow")
        shadowed, shadow_bytes = write_shadow_lod(game, engine, body.name, None if variant is None else variant.shadow)
    except ValueError as exc:
        raise ValueError(f"--player-character {variant.name if variant is not None else species!r}: W36: {exc}"
                         ) from None
    coloured = []
    tinted = variant is not None and bool(variant.colours)
    copied = tinted and not himself   # Step 2.206: on his own rig his rows in place, no copy
    worn_only = player_only and body.name.casefold() != PLAYER and (lo.copied or lo.hide or remeshes(variant))
    alone = (copied or worn_only) and copy_alone(game, body.name)   # AZ-761: the game loads W38's copy without it
    restored = worn_only and not alone   # P2 (Step 2.203, D543): where a level places a critter wearing the body
    if tinted or restored:   # W38 and X47 (Step 2.170b; D539, D734): the player's copy of its body, recoloured
        # after every other write of it, which the player's species alone binds; P2: its prop and mesh in it alone
        try:
            if himself:   # Step 2.206: his own rows in place (Step 2.170c), only he wearing his body
                grown, _, coloured = write_colours(bytes(game["characters.xbr"]), bytes(game["index.xbr"]), body.name,
                                                   located(variant.colours, variants.colour_folder(variant)),
                                                   in_place=True)
                index = bytes(game["index.xbr"])
            else:
                grown, index, coloured = write_colours(bytes(game["characters.xbr"]), bytes(game["index.xbr"]),
                                                       body.name, located(variant.colours,
                                                                          variants.colour_folder(variant))
                                                       if tinted else ())
                if restored:
                    grown = npc_body(grown, game.stored("characters.xbr"), body.name)
                install_body_key_shim(game["default.xbe"], grown, index, body.name)
        except ValueError as exc:
            raise ValueError(f"--player-character {variant.name if variant is not None else species!r}: {exc}"
                             ) from None
        game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
    toss_info = None
    if toss is not None:   # W30 and X42 (Step 2.159b; D473): the projectile as data, thrown from the hand
        try:
            grown, index, toss_info = (
                throws.write_projectile(bytes(game["characters.xbr"]), bytes(game["index.xbr"]),
                                        game.stored("default.xbe"), style.throw) if shot is None else
                throws.write_template(bytes(game["characters.xbr"]), bytes(game["index.xbr"]),
                                      game.stored("default.xbe"), game.stored("fx.xbr"), shot, toss.scale))
            game["characters.xbr"], game["index.xbr"] = bytearray(grown), bytearray(index)
            install_throw_shim(game["default.xbe"], toss.table(), trampoline_symbol_va(
                game["default.xbe"], SEARCH_HOOK, SEARCH_RADIUS_SYMBOL, CHECKOUT, shim_source=SEARCH_SHIM.source_path()))
        except ValueError as exc:
            raise ValueError(f"--player-character {species!r}: its throw: {exc}") from None
    waves = [NewResource(f"{variants.sound_dir(variant)}/{leaf}", "wave", wave_entry(samples))
             for leaf, samples in made_waves.items()]
    waves += [NewResource(key, "wave", wave_entry(samples)) for key, samples in kit_waves.items()]
    # X32's flash (D700) first, numbered from fx.xbr's count, then the variant's sounds (Step 2.141) and the kit's
    # (Step 2.159a), last: the fx doc's buffer is replaced
    flash = hit_flash(game.stored("fx.xbr"), game.stored("default.xbe")) if hit_fx else []
    try:   # X37's stream (AZ-759, D764) after it: each drain hit's particles into the player's chest
        stream = (drain_stream(game.stored("fx.xbr"), game.stored("characters.xbr"), game.stored("default.xbe"),
                               chest, len(parse_toc(game.stored("fx.xbr"))) + len(flash)) if drain else [])
    except ValueError as exc:
        raise ValueError(f"--player-character {variant.name if variant else species!r}: its drain stream: {exc}") \
            from None
    if flash or stream or waves:
        try:
            game["fx.xbr"] = bytearray(append_resources(bytes(game["fx.xbr"]), [*flash, *stream, *waves]))
            game["index.xbr"] = bytearray(add_index_records(
                bytes(game["index.xbr"]),
                [IndexRecord(e.name, "fx.xbr", e.tag) for e in (*flash, *stream, *waves) if e.name]))
        except ValueError as exc:
            raise ValueError(f"--player-character {variant.name if variant else species!r}: its "
                             f"{'hit flash and ' if flash else ''}{'drain stream and ' if stream else ''}sounds: "
                             f"{exc}") from None
    alone = alone and copied   # AZ-761: the game loads W38's copy without the body (P2 makes none there)
    lod_copies = 2 if copied and not alone and not restored else 1   # W38's copy carries W36's and W39's LODs
    # again, P2's body vanilla's; none on himself (Step 2.206: his rows in place)
    budget = _load_budget(game, body.name, variant.name if variant is not None else species, bool(waves), ram,
                          shadow_bytes * lod_copies, lods_bytes * lod_copies, alone)
    eased, over = "X22" in late, "X23" in late
    named = "" if body.name == species else f" ({body.name})"
    if picks:
        roll = picks[columns.index(ROLL)]
        attacks = sorted({p for col, p in zip(columns, picks) if col != ROLL})
        moved = " on garret4's root motion (X4)" if roll_shim else ""
        slot = {i: c for i, (c, _) in fills.items()} | {
            i: c for i, name in enumerate(BASE_CLIPS) for c in body.clips if c.casefold() == name}
        hit = next((slot[i] for i in (0x25, 1) if i in slot), roll)
        bake = sum(c.startswith(BAKED_DIR) for c, _ in fills.values())
        own = len(fills) - bake
        filled = ", ".join(
            ([f"its own clips in {own} base clip slots it lacks"
              f"{f' ({len(timed)} in garret4\'s time, X12)' if timed else ''}"] if own else [])
            + ([f"garret4's baked onto its rig in {bake} (characters/{body.name}/{BAKED_DIR}, B)"]
               if bake else []))
        filled = f", {filled} (X11, anims {missing_anims})" if filled else ""
        climb = next((c for c in _CLIMB_STAND_INS if c in body.clips), roll)
        clips = (f"the roll plays {roll}{moved}, the attacks {', '.join(attacks)}, "
                 + (f"a hit {hit} in garret4's 0.4 s (X7)" if not himself else f"his hit {hit}")
                 + filled
                 + (f", a ladder or a hoist {climb} (X9)" if needs_climb_shim(body) else ""))
    else:
        clips = (f"its body has no clips, so garret4's play as timers in {len(fills)} base clip "
                 "slots and every attacks_anims column, baked onto it with his root motion "
                 f"(characters/{body.name}/{BAKED_DIR}, B), with his hit box and window on each (X11, X12, X3)")
    named += f", {MODE_NAMES[mode]}"
    if mode == "garret4":
        named += (": garret4's height" if sized is not None else ": garret4's scale") + (
            ", each attack and the roll in garret4's time" if picks else "")
    elif mode == "own" and picks:
        named += ": the roll in garret4's time" + (
            f", {len(short)} attacks over before their window can hit in garret4's time too "
            f"({', '.join(short)})" if short else "") + (
            f", {len(banded)} attacks' damage window opening by {WINDUP_MAX:g} s ({', '.join(banded)})"
            if banded else "")
    if mode != "garret4" and sized is not None:
        named += ", garret4's height"
    elif size == "garret4" and sized is None:
        named += ", its own size (no height to measure)"
    if model_scale != 1.0:
        named += f", drawn x{model_scale:g} that size"
    if stride:
        named += f", its stride ({', '.join(f'{k} {v:g}' for k, v in stride.items())})"
    sized_eye = plan.x8 and sized is not None and math.isclose(plan.aim * sized, eye_height(characters))
    aim = ("garret4's eye height" + (f" x{model_scale:g}" if model_scale != 1.0 else "")
           if sized_eye else "garret4's share of the body's height")
    m0, m1 = plan.margins
    rise = 0.5 * rest_distance(plan.s if plan.rig else 1.0) - m0   # the camera over the water at least
    swims = "where garret4's sits over his root (W27's m_eye)" if surfaced else "the same"
    eye = ("" if not plan.x8 else f"; the camera aims at {aim}, {plan.aim * drawn:.2f} m up, "
           f"and swimming {swims} with the camera at least {rise:.2f} m over the surface, or once "
           f"its top is under in a dive {m1:.2f} m under it, never above its top (X8)"
           + (f", keeping its distance where a line {plan.lift:.2f} m lower is clear (X19)"
              if plan.lift >= EYE_LIFT_MIN else ""))
    if not plan.x8 and plan.lift >= EYE_LIFT_MIN:
        eye = f"; the camera keeps its distance where a line {plan.lift:.2f} m lower than its m_head is clear (X19)"
    if plan.x20:
        eye += "; on the zipline the camera aims no lower than the body's centre (X20)"
    if plan.rig:
        eye += (f"; the camera framed for a body {plan.s:.3g} x garret4's size: rest "
                f"{rest_distance(plan.s):.2f} m (X25)")
    if plan.near:
        eye += "; its body drawn however near the camera comes to its centre (X27)"
    where = ("at the hands {} and {}".format(*hands) if hands else
             f"{'where its m_damage hits' if point.kind == 'marker' else 'in front of its chest'} "
             f"at ({', '.join(f'{v:.2f}' for v in point.point)})")
    at_hands = (f", its particles and power heads at its staff's {' and '.join(hands)} (W4 and W6 left out"
                + (f"; {heads.note}" if heads is not None else "") + ")"
                if lo.native else f", its particles {where} (W6), its power heads {heads.note} (D707)")
    style_columns = sum(p in style_hits for p in picks)
    reach = ((", garret4's own hit box and window on each attack (X3)" if mode == "garret4" else
              ", its hit boxes at its prop's tip (X3, below)" if tipped is not None else
              f", garret4's own attacks in {borrowed.bit_count()} columns baked onto its rig (B, X12) with his "
              "hit box and window on each (X3)" if borrowed else
              f", {style.source}'s own build's {len({p for p in picks if p.startswith(style.dir)})} clips in "
              f"{sum(p.startswith(style.dir) for p in picks)} columns baked from his rig as {style.dir}<clip> (Step "
              "2.161c), a hit box at its hand for each, on in his own damage window where he has one, else X3's "
              "(X3)" if style is not None and style.own is not None else
              f", the bare-hands kit's {len(set(p for p in picks if p in style_hits))} clips in {style_columns} columns "
              f"baked from {style.source}'s rig as {style.dir}<clip> (Step 2.159a), a hit box at the fist or foot "
              "each clip strikes with (Step 2.195), on in the kit's window (X3)" if style_columns else
              ", a hit box at its action point for the clips without one"
              + (f" and the {missed.bit_count()} attacks whose own box can't reach a target on the ground"
                 if missed else "") + " (X3)")
             if marker or tipped is not None else "")
    turns = (f", each swing the next of {len(rotate[0])} attack clips (X10)"
             if rotate else "")
    if attack_reach != 1.0:
        reach += f", hit boxes reaching {attack_reach:g} times as far (X13)"
    if mask:
        reach += (f", every attack's box ({mask.bit_count()} of {len(columns) - 1} columns) "
                  "reaching back to the feet, across the facing line and down to the floor (X13)")
    turning = rotate[1] if rotate else 0
    weighed = [b for i, b in enumerate(factors) if b is not None and not (carry and turning >> i & 1)]
    weighed += [b for row in (entries if carry else []) for b in row if b is not None]
    if weighed:
        reach += (f", the attack balance (W14): each attack's damage x{min(weighed):.2f} to "
                  f"x{max(weighed):.2f} garret4's" + (
                      f" (a slow attacker: x{lift[0]:.2f} the balance's, D350)" if lift and lift[1] else
                      f" (garret4's damage on one enemy: x{lift[0]:.2f} the balance's, D389)" if lift else "") + (
                      f", {bump.bit_count()} short melee attacks reaching x{REACH_BUMP:g} (X13)" if bump else ""))
    if (picks or timers) and attack_damage != 1.0:
        reach += f", attack damage x{attack_damage:g}"
    if heavy or unstunned:
        reach += (", its hits stunning as garret4's in the "
                  + " and ".join(([f"{heavy.bit_count()} light columns"] if heavy else [])
                                 + ([f"{unstunned.bit_count()} columns its sets play for basic1-3"]
                                    if unstunned else []))
                  + " whose damage multiplier reaches 1.0 (X18)" + (", its drain's hits there too" if light_at else ""))
    elif light_at:
        reach += ", its drain's hits stunning where its own do (X18)"
    if chain == "any":
        reach += ", the combo's next attack on any press in its window, hit or miss (chain any, D1045)"
    if chained:
        reach += (f", the combo chaining {CHAIN_AFTER_HIT:g} s after the first hit, or {round(30 * STUN_LAG)} "
                  f"ticks after the box meets a target ahead, in {', '.join(chained)} (W19)")
    if far > SEARCH_RADIUS:
        reach += f", the combo chaining on a stunned target out to {far:.2f} m where none is within 3 m (X21)"
    if (picks or timers) and attack_speed != 1.0:
        reach += f", attack speed x{attack_speed:g}" + (
            f", {', '.join(sped)} chaining inside the stun" if sped else "") + (
            f", its hits' no-hit window / {attack_speed:g} (X31)" if windowed else "")
    wings = "; the air armor's wings stroke on each flap (X16)" if needs_wings_shim(body) else ""
    if ringed is not None and ringed.rows:
        wings += ("; its ranged attacks' effects in their own instances, played out where the next clip leaves them ("
                  + ", ".join(f"{k.name} {'EPSB'[k.mode]} x{k.slots}" for k in ringed.keys)
                  + f", {len(ringed.clips)} clips in {ringed.mask.bit_count()} columns"
                  + (f" and {sum(r >= fx_ring.COLUMNS for r in ringed.rows)} X10 entries"
                     if any(r >= fx_ring.COLUMNS for r in ringed.rows) else "") + ", X38)")
        stand = ((worn.fx_ring or {}) if worn else {}).get("stand") or {}
        if stand.get("fx"):   # Step 2.155b (D501)
            wings += (f"; its stand key the player's clone of {stand['key']}, retuned at {len(stand['fx'])} records "
                      "(every NPC keeps the vanilla graph)")
    for e, b, (anchor, at, grow, nbytes, values) in zip(shields, bound, holders):   # Step 2.167c (D538's E3)
        t = e.template
        wings += (f"; its {t.name} row (template {t.name}@{fx_templates.template_sha(t.name)}): a {t.group} on "
                  f"{', '.join(e.columns)} (" + ", ".join(f"{k} {v:g}" for k, v in values.items())
                  + (f", colour {list(e.colour)}" if e.colour is not None else "")
                  + f"), {b.key} ({b.records} records, {nbytes} B; no NPC plays it), its holder "
                  + (f"bound to {anchor}" if anchor else
                     f"at ({', '.join(f'{c:.3f}' for c in at)}) x{grow:.3f}")
                  + f", shown while the column's clip plays, fading over {b.fade:g} s and gone {b.tail:g} s later "
                  "(X38's bound key)")
    if ringed is not None and ringed.left_out:
        wings += "; no X38 copy for " + ", ".join(ringed.left_out)
    if hit_fx:   # Step 2.180 (D700)
        wings += (f"; its plain hits{f' and its {shot.template.name}' if shot is not None and shot.template.hit else ''}"
                  f" show a small flash of its own, {HIT_FLASH} ({len(flash)} entries in fx.xbr: {HIT_FLASH_SOURCE} at "
                  "half its size, faster and fainter), never an element power's effect (X32)")
    if carried:
        wings += (f"; {carried.bit_count()} attacks move with the stick at its run speed and turn as it walks "
                  f"({'a flyer' if species in FLYERS else 'its spins'}, X33)")
    if held:
        wings += f"; {held.bit_count()} attacks chain while A or B is held, planted (X33's held mask)"
    if looped is not None:
        chains = f", sweep1 chaining at {looped[1]:.4f} too" if looped[2] else ""
        wings += (f"; B's hand spin chains planted: sweep2 from {looped[0]:.4f} to {looped[1]:.4f} of its clip, B "
                  f"looping it, a running B starting at sweep1{chains}, a press in her rest on the hand chaining as "
                  "well (W37)")
    if blasts:
        wings += (f"; its air attack's bolt held in the air short of {impact:g} s and its blast played where it lands, "
                  "its clip at that time on the first ground tick, a hard landing landing soft (X39)")
    if seek:
        wings += (f"; its {', '.join(c for i, c in enumerate(columns) if seek >> i & 1)} turn at the attack's start to "
                  f"the critter nearest the heading within {kit_document()['throw']['range']:g} m and "
                  f"{kit_document()['throw']['cone']:g} deg (X49)")
    if toss is not None and shot is not None:   # Step 2.167b (D538's E2)
        t, v = shot.template, shot.values
        wings += (f"; its {t.name} row (template {t.name}@{fx_templates.template_sha(t.name)}): "
                  + ", ".join(f"{columns[c.column]} throws it out at tick {c.release} of {c.ticks}, in the hand from "
                              f"{c.spawn}, x{c.mult:g}" for c in toss.shots)
                  + f" (W30: {throws.SPECIES} wearing "
                  + ("our own arrow" if "authored" in t.body else f"a copy of {toss_info['source']}")
                  + f" at x{toss.scale:.3f}, {v['size']:g} m"
                  + (f", recoloured {list(shot.colour)}" if toss_info["recoloured"] else "")
                  + f"; its fx {', '.join(t.sets) or 'none'} grafted ({toss_info['grafted']} records), its break "
                  + (f"a copy of {toss_info['impact']}" if toss_info["impact"] else "none")
                  + f"; {len(toss_rows)} config rows, {len(toss_info['named'])} named entries, "
                  f"{toss_info['bytes']} B) at {toss.speed:g} m/s, arc {toss.arc:g} (the share of gravity it falls "
                  f"with), life {toss.life:g} s, radius {toss.radius:g} m, {toss.pushout:.3f} m out from its axis, "
                  + (f"onto the critter nearest its facing within {toss.range:g} m and {toss.cone:g} deg, else "
                     f"{toss.miss:g} m on" if toss.seek else f"straight along its facing to {toss.miss:g} m on")
                  + ", as the player's hit (X42), on top of each column's own swing; the logic on the melee reach "
                  "(D474)")
    elif toss is not None:
        tw = style.throw
        wings += (f"; its {columns[toss.column]} throws {'her vase' if d.take else 'a vase' if tw.kind == 'vase' else 'a rock'}"
                  f" (W30: {throws.SPECIES} wearing "
                  + (f"{tw.projectile['source']}'s LOD0 vase, its break's shards in its colour"
                     if tw.kind == "vase" else f"a copy of {tw.projectile['source']}")
                  + f" at x{toss.scale:.3f}, its break harmless; {len(toss_rows)} config rows, "
                  f"{len(toss_info['named'])} named entries) from the hand: in it from tick {toss.spawn}"
                  + (f" (her hand {d.take[1]:.3f} model units from her vase; it is back in her hand at {tw.back})"
                     if d.take else "")
                  + f", out at {tw.release} of {tw.ticks} {toss.pushout:.3f} m from its axis at {tw.projectile['speed']:g} m/s"
                  f" straight along its facing to {tw.miss:g} m on,"
                  f" its hits the player's at x{toss.mult:g} (X42); a new press of A throws again at tick {tw.chain},"
                  " a held A once (D566), the logic on the melee reach (D474)")
    if sets:
        wings += (f"; WHITE cycles its {len(sets)} attack set{'s' * (len(sets) > 1)} ("
                  + " | ".join(line.replace("\n", ": ", 1).replace("\n", " ") for line in lines)
                  + "), the set's line shown in the HUD's top-left corner for 2 s, and the stick's direction picks no attack (X36)")
    if armor:
        k = body_height(characters, body) / garret4.top
        wings += (f"; the armor on the body, x{k:.2f} garret4's size in its model ({armor} transforms, W15), "
                  "each piece riding a bone of it (X16)" if needs_wings_shim(body) else
                  f"; the armor on the body, x{k:.2f} garret4's size in its model ({armor} transforms, W15)")
    if walls:
        wings += ("; no staff-hits-wall sweep, as the body has no staff (X17)" if not lo.cut else
                  "; his staff cut from his mesh (W33), and no staff-hits-wall sweep of it (X17)")
    npcs = ("" if restored else "; no level places a critter wearing this body" if worn_only else
            "; every NPC wearing this body holds it too")   # P2 (Step 2.203): the player's copy's line below
    if lo.carry == IN_PLACE:
        wings += (f"; its {lo.prop.clip} carried along garret4's staff, its element effects at its ends"
                  + (", its hit boxes grown to its tip" if reaching else "") + " (W26)")
    elif lo.carry == COPY:   # Step 2.161b
        wings += (f"; its weapon {lo.weapon.name} (--player-weapon): the {lo.prop.title} held in its {lo.grip} on "
                  f"{' and '.join(lo.prop.carriers)} (W31), keyed along garret4's staff in its own hand's frame in "
                  f"every baked clip, its mesh x{lo.k:.3g} in {propped} LOD{'s' * (propped > 1)} with its material "
                  "copied (W32), "
                  + ("garret4's staff effects bound to its ends by name" if lo.native else
                     "its element effects at its ends")
                  + (", its hit boxes grown to its tip" if reaching else "")
                  + npcs)
    elif lo.carry in (RIGID, FLOAT):   # Step 2.161e (D493)
        wings += (f"; its weapon {lo.weapon.name} (--player-weapon): the {lo.prop.title} "
                  + (f"held rigidly in its {lo.grip} on {' and '.join(lo.prop.carriers)} (W31), where its own clips "
                     "carry it" if lo.carry == RIGID else
                     f"on a floating carrier at its root, {lo.prop.carriers[0]} (W31), keyed along garret4's staff in "
                     "each of his clips baked onto it")
                  + f", its mesh x{lo.k:.3g} in {propped} LOD{'s' * (propped > 1)} with its material copied (W32), "
                  + ("garret4's staff effects bound to its ends by name" if lo.native else
                     "its element effects at its ends")
                  + (f", X3's box a {tipped.rows[0 if columns[0] != ROLL else 1][5]:.2f} m cube at its tip on "
                     f"{tipped.columns.bit_count()} attack columns in the windows of its own clips, in place of its "
                     "own boxes and its second (X3)" if tipped is not None else
                     ", his hit boxes grown to its tip" if lo.carry == FLOAT else ", a look only (Skin)")
                  + npcs)
    elif d.magic is not None:   # Step 2.161c
        m, caster = d.magic, lo.cast or style
        wings += (f"; its weapon {lo.name} (--player-weapon): the {len(m.grown)} markers {caster.source}'s fx_default "
                  f"binds that it lacks grown ({', '.join(n for n, _ in m.grown)}), "
                  + (f"{', '.join(m.ridden)} keyed in each of "
                     + ("the copies of the clips its attack columns play, " if d.cast[0].startswith(CAST_DIR) else
                        "garret4's timers its attack columns play, " if d.cast[0].startswith(BAKED_DIR) else
                        "its own ")   # Step 2.204 (D810): no attack clip of its own
                     + f"{', '.join(d.cast)} at its {m.grip} plus his "
                     f"offset from his {m.source_grip}, his {CAST_SWITCH} on over each one's own damage window, "
                     "its own boxes hitting (Step 2.161e), " if d.cast else
                     f"{', '.join(m.ridden)} keyed in each of his clips at its {m.grip} plus k x his offset from his "
                     f"{m.source_grip}, " if m.ridden else "")
                  + f"the player's clone of his graph, {fx_edit.clone_key(body.name)}, with his own build's retune"
                  + "".join(f", {n} bound to its {to}" for _, n, to in m.renames)
                  + (", in place of its own default fx" if m.replaced else "")
                  + " (W34, X40); every NPC wearing this body keeps its own")
    elif lo.picked:
        wings += f"; its weapon {lo.name} (--player-weapon)" + (   # Step 2.161g (D592)
            f": {lo.weapon.style.title} ({', '.join(sorted(worn.clips))}) generated on its own rig under "
            f"characters/{body.name}/{variants.VARIANT_DIR} in {len(recipe_picks)} columns (W22), their boxes "
            f"x{lo.k:.3f}" + (f", its {', '.join(lo.left)} its other picks" if lo.left else "")
            if lo.lent and worn.clips else "")
    if kept_up:
        wings += f"; its {lo.prop.title} kept over the floor in {len(kept_up)} of its own clips (W41)"
    if faded:
        wings += f"; its {lo.prop.title} kept over the floor through the crossfades of {len(faded)} clips (W41)"
    if lo.hide:
        wings += f"; its own {lo.default.prop.clip} hidden (W33)" + (
            "" if restored else ", on every NPC wearing this body too")
    if eased:
        wings += (f"; on the zipline it hangs x{hung:.3f} garret4's grab below the cable, its top where his (X9), easing to its "
                  f"stance at most {HANG_STEP.default:g} m a tick on the let-go and at the cable's end (X22)")
    if hold is not None and hold.needed:
        wings += (f"; its drawn hang, {hold.span:.2f} m under the cable, held over the floors under its path, "
                  f"rising early ({hold.ahead} ticks ahead on the ride, its hang_start's dips ahead) at most "
                  f"{HOLD_STEP.default:g} m a tick (X28)")
    if hold is not None and hold.fade_ray > 0.0:
        wings += ("; off the zipline, at a landing and at a takeoff its crossfade is drawn on the floor where its "
                  "pose dips through it (X48)")
    if over and "X26" in late:
        wings += ("; over a ladder's top its drawn feet land on the floor (X23) and it settles into its stance there "
                  "(X26)")
    elif over:   # a body with no clips (Step 2.127): its root rides garret4's m_feet / D
        wings += "; over a ladder's top it starts where it hangs (X23) and is drawn where it stands"
    if fielded:
        wings += ("; its own field's damage taken as the species takes it ("
                  + ", ".join(f"{kind} {v:g}" for kind, v in fielded.items()) + ", W16)")
    for into, without in ((SELF_DIR, "without the switch of its own damage field (W17)"),
                          (QUIET_DIR, "without the markers that start its default fx's camera or critter generator "
                                      "(W22)"),
                          (CENTRED_DIR, "drawn about its centre at its size (AZ-623)")):
        if mine := {clip: name for clip, name in copies.items() if name.startswith(into)}:
            wings += ("; " + ", ".join(f"its {clip} played as characters/{body.name}/{name}"
                                       for clip, name in mine.items()) + f", {without}")
    if drain:
        wings += (f"; its {', '.join(sorted({picks[i] for i in range(len(columns)) if drain >> i & 1}))} in "
                  f"{drain.bit_count()} column{'s' * (drain.bit_count() > 1)} drains the critter it lands on within {DRAIN_RANGE:g} m at "
                  f"any bearing, never its wearer, {DRAIN_SHARE:.0%} of the damage back as HP from "
                  f"{'each critter its box touches' if every else 'it alone'}, each drain hit streaming red particles "
                  f"from the critter into the player's chest ({DRAIN_STREAM}, {len(stream)} entries in fx.xbr) (X37)")
    if bolts[1]:
        wings += (f"; its beam's bolts in {bolts[0].bit_count()} columns on the chest of the critter in its box "
                  f"({bolts[2]:.2f} m ahead, {bolts[3]:.2f} m either side of the swing), the drain's pick first, else "
                  f"straight ahead to {bolts[2]:.2f} m at {bolts[4]:.2f} m up (X37, AZ-769)")
    if ranged:
        wings += f"; past {finish:.2f} m, its blast's reach, its combo ends on finish3, the beam, nearer on finish (W40)"
    if swim:
        wings += (f"; its swim plays its {swim[SWIM_SLOT][0][len(SWIM_HOLD_DIR):]} once, then holds its last pose, "
                  f"bobbing {SWIM_BOB[0]:g} model units every {SWIM_BOB[1]:g} s, as "
                  f"characters/{body.name}/{swim[SWIM_SLOT][0]} (W25)")
    if surfaced:
        wings += (f"; its swim plays copies under characters/{body.name}/{SURFACE_DIR} keyed {SURFACE_MARKER} at its "
                  f"root, so it swims at the surface as garret4 does, and {SURFACE_EYE} at his head over his root (W27)")
    if quiets:
        quieted: dict[str, list[int]] = {}
        for slot, (name, _) in sorted(quiets.items()):
            quieted.setdefault(name, []).append(slot)
        wings += ("; " + ", ".join(
            f"its {name[len(QUIET_DIR):]} played as characters/{body.name}/{name} in slot"
            f"{'s' if len(slots) > 1 else ''} "
            + (f"{slots[0]}-{slots[-1]}" if len(slots) > 1 and slots[-1] - slots[0] == len(slots) - 1
               else ", ".join(map(str, slots)))
            for name, slots in quieted.items())
                  + ", without the markers that start its default fx's camera or critter generator (W22)")
    if size_s != 1.0:
        wings += f"; {touch_words(size_s)}, {walk_words(walk)}"
    if voiced:
        made = {name: (sum(variants.take_name(name, k) in made_waves for k in range(variants.TAKES)), len(p["columns"]))
                for name, p in sorted(heard.sfx.items())}
        voice = describe_variant(roles, emptied, columns, made, len(waves), sum(len(e.payload) for e in waves), [
            f"{d.origin} {d.path.name}: {leaf} (sha256 {d.sha256[:12]}), {len(d.samples) / SOUND_RATE:.3f} s from {d.info.rate} Hz, "
            f"{d.info.channels} channel{'s' * (d.info.channels > 1)}, {d.info.bits}-bit"
            + (f"; past the game's longest inline wave ({LONGEST_WAVE} s), unseen in game"
               if len(d.samples) / SOUND_RATE > LONGEST_WAVE else "") for leaf, d in sorted(drop.items())])
    else:
        voice = describe(roles, emptied) if roles else [
            "  Player model sounds: Garret's (--player-character-sounds garret4)"]
    if kit_waves:   # Step 2.159a (D502)
        voice.append("    bare hands (D502): " + ", ".join(
            ([f"its whoosh in {len(swung)} columns, {len(swing)} takes"] if swing else [])
            + ([f"a thud, {thud[0]}, on its plain hits in the victim's hit sound's place (X43)"] if thud else []))
            + f"; {len(kit_waves)} wave{"s" * (len(kit_waves) != 1)}, {sum(len(wave_entry(v)) for v in kit_waves.values())} B, in fx.xbr")
    overlaid = [] if not w23 else [   # W23 (Step 2.140)
        f"  Player model: {species}'s own build retunes the player's clone of characters/{body.name}/fx/"
        f"fx_default, {fx_edit.clone_key(body.name)}, at {len(worn.fx)} records "
        f"({', '.join(e['name'] for e in worn.fx)}) (W23, X40); every NPC of that body keeps its own"
    ] if not worn.clips else [
        f"  Player model: {species}'s own build plays its {', '.join(sorted(worn.clips))} under "
        f"characters/{body.name}/{variants.VARIANT_DIR} on {', '.join(columns[i] for i in sorted(recipe_picks))}, "
        "which X33 doesn't carry and X13 doesn't fill (W23)"
        + (f"; held, {', '.join(columns[i] for i in range(len(columns)) if thrown >> i & 1)} throw again as each "
           "box arrives (X33's held columns, Move end1)" if thrown else "")
        + ("; its hits through walls (garret4's hitsThroughWalls 1.0)" if worn.through_walls else "")]
    recipe = overlaid if variant is None else [
        f"  Player model: {variant.name}, a variant of {species} (recipe {variant.sha}, "
        + (f"sounds {variants.sounds_sha(heard, drop)}, " if voiced else "") + f"{variant.source}): "
        + "; ".join(([f"its {', '.join(worn.markers)} grown after the bake"] if worn.markers else [])
                    + ([f"its clips {', '.join(sorted(worn.clips))} under characters/{body.name}/"
                        f"{variants.VARIANT_DIR} in {len(recipe_picks)} columns (W22)"] if worn.clips else
                       [f"its own moves dropped: {lo.weapon.title}'s in every column (D585)"] if lo.weapon is not None
                       else [])
                    + ([f"{carried.bit_count()} of them moving with the stick (X33)"] if carried and worn.clips else [])
                    + ([] if worn.rotate or not worn.clips else ["no X10 ring"])
                    + (["its hits through walls (garret4's hitsThroughWalls 1.0)"] if worn.through_walls else [])
                    + ([f"the player's clone of characters/{body.name}/fx/fx_default, "
                        f"{fx_edit.clone_key(body.name)}, retuned at {len(variant.fx)} records"
                        + "".join(f", {g.get('template') or g['from']['key']} grafted under record {g.get('parent')}"
                                  for g in variant.fx_grafts)
                        + "".join(f", {e['name']}'s material {', '.join(f'{k} {v:g}' for k, v in e['material'].items())}"
                                  for e in variant.fx if "material" in e)
                        + " (X40); every NPC of that body keeps its own"] if variant.fx_edits else [])
                    + ([] if reshaped is None else [_reshaped_line(reshaped, variant, rows, species, restored)])
                    + ([f"its arms {variant.arms:g} deg wider in {styled} clips, all but its recipe's v/ ones (W28)"]
                       if variant.arms else [])
                    + ([_jiggle_line(rigged, peaks, variant, sprung, jiggle_strength, jiggle_stiffness)]
                       if rigged is not None else [])
                    + ([f"its textures (W30): {'; '.join(painted)}"] if painted else [])
                    + ([f"his colours in his own body's rows, in place (W38, no copy: only he wears it): "
                        f"{'; '.join(coloured)}"] if variant.colours and himself else
                       [f"its colours in the player's copy of its body, {skin_key(body.name)}, which only the "
                        f"player binds (W38, X47): {'; '.join(coloured)}"] if variant.colours else [])
                    + ([_idles_line(variant)] if variant.idles else [])
                    + ([_slots_line(variant, stride)] if variant.slots else [])
                    + ([f"its victories end at a push of the stick {variant.victory_cancel:g} s in, else play "
                        "whole (X46)"] if variant.victory_cancel is not None else []))]
    return [*recipe, f"  Player model: {PLAYER} wears {species}'s body{named}"
            f"{f', scale {scale:g}' if scale is not None else ''}; {clips}; "
            f"{len(staff)} staff transforms hidden{at_hands}{reach}{turns}{eye}{wings}",
            *([_hair_line(sprung, jiggle_strength, jiggle_stiffness)] if hair else []),
            *voice,
            *([victories_line(fills | victory, body, timers=timers,
                              recipe=recipe_fills(variant.slot_clips()) if variant is not None else None)]
              if not himself else []),
            *laid,
            *shadowed,
            *([f"  Player model: its {' and '.join(w for w, on in (('prop', lo.copied or lo.hide),
                                                                  ('mesh', remeshes(variant))) if on)} in the "
               f"player's copy of its body, {skin_key(body.name)}, which only the player binds (P2: W38's copy, X47); "
               f"every NPC wearing {body.name} draws vanilla's body"] if restored else []),
            *budget,
            f"  Player model status: {colour} ({why})"]


def _shadow_ratio(body: str, lod0: list, cast: bool, shadow: bool | float | None) -> float | None:
    """The share of LOD 0 W36 cuts ``body`` to (:func:`write_shadow_lod`),
    ``None`` for no cut; :class:`ValueError` where it refuses."""
    from azurkit.tools.characters import decimate

    if shadow is False or shadow is None and not (
            len(lod0) == 1 and cast and decimate.drawn(lod0[0]) > decimate.SHADOW_MIN):
        return None
    if len(lod0) != 1:
        raise ValueError(f"lods.shadow: {body} has {len(lod0)} LODs, and the shadow draws its own LOD 1")
    if not cast:
        raise ValueError(f"lods.shadow: {PLAYER} casts no realtime shadow (no shadowSize, or a shadowTextureName), "
                         "so nothing would draw a shadow LOD")
    return decimate.SHADOW_RATIO if shadow is None or shadow is True else shadow


def _shadow_ahead(characters: bytes, engine, player_body: str, body: str, shadow: bool | float | None) -> None:
    """W36's cut of ``body`` as a variant's W24, W29 and W30 leave it in
    ``characters`` (the player's row still wearing ``player_body``), in a
    worker process while the build goes on (Step 2.179: booblord_high's
    was a sixth of her build; :func:`~azurik_mod.assets.decimate.cut_ahead`),
    where :func:`write_shadow_lod` would cut it: W36 takes it if its LOD 0
    is still this one, and refuses as it would.  Once a body: a dress of
    the kept body (:data:`_KEPT_BODY`) while its cut runs starts none."""
    from azurkit.tools.characters import decimate, lods
    from azurkit.tools.characters.body_codec import read_asset

    if shadow is False or decimate.ahead_of(characters):
        return
    lod0 = read_asset(characters, body).lods
    cast = any(w.shadow for w in lods.wearers(bytes(engine.document.raw), player_body) if w.species == PLAYER)
    try:
        ratio = _shadow_ratio(body, lod0, cast, shadow)
    except ValueError:
        return
    if ratio is not None:
        decimate.cut_ahead(lod0[0], ratio, source=characters)


def write_shadow_lod(game, engine, body: str, shadow: bool | float | None = None) -> tuple[list[str], int]:
    """W36 (Step 2.166c, the X.68 audit's item 5): the body the player
    wears, ``body``, given a shadow LOD; its log line and the bytes its own
    runs grew by.  The player's
    realtime shadow draws LOD 1, LOD 0 for a one-LOD body
    (:mod:`~azurik_mod.assets.lods`), so a big one-LOD body is drawn twice a
    frame; here it takes a LOD 1 cut from its LOD 0
    (:func:`~azurik_mod.assets.decimate.shadow_lod`) that only the shadow
    draws: every wearer whose switch distances would draw it on screen
    before its ``farClip`` (garret4's 1000 m is his farClip; town_female_2's
    15 m) gets ``lodThreshold1`` FLT_MAX.  ``shadow`` is the recipe's
    ``lods.shadow`` (``_player_variants``): ``None`` a cut at
    :data:`~azurik_mod.assets.decimate.SHADOW_RATIO` for a one-LOD body
    past :data:`~azurik_mod.assets.decimate.SHADOW_MIN` triangles while
    garret4 casts a realtime shadow, else nothing; ``False`` nothing;
    ``True`` or a share, that cut on any one-LOD body, :class:`ValueError`
    for one with more LODs or with no realtime shadow to draw it.  The LOD
    adds its own runs to the load (:func:`_load_budget` counts them and
    names ``"lods": {"shadow": false}`` when they alone pass its line)."""
    from azurkit.tools.characters import decimate, lods
    from azurkit.tools.characters.body_codec import read_asset
    from azurkit.tools.characters.model_inspect import MiB, own_runs

    if shadow is False:
        return [], 0
    characters = bytes(game["characters.xbr"])
    lod0 = read_asset(characters, body).lods
    worn = lods.wearers(bytes(engine.document.raw), body)
    ratio = _shadow_ratio(body, lod0, any(w.shadow for w in worn if w.species == PLAYER), shadow)
    if ratio is None:
        return [], 0
    grown, cut = decimate.shadow_lod(characters, body, ratio)
    hidden = [w.species for w in worn if lods.spans(w.thresholds, w.far, 2)[1] is not None]
    for species in hidden:
        set_keyed_double(engine, species, "lodThreshold1", lods.FLT_MAX)
    added = own_runs(grown, body)["bytes"] - own_runs(characters, body)["bytes"]
    game["characters.xbr"] = bytearray(grown)
    return [f"  Player model: {body}'s shadow LOD (W36): LOD 1, {decimate.drawn(cut)} of LOD 0's "
            f"{decimate.drawn(lod0[0])} triangles (cut at {ratio:g} within {decimate.SHADOW_ERROR * 100:g} cm), drawn "
            f"only in {PLAYER}'s realtime shadow, "
            f"{added / MiB:.2f} MiB more own runs"
            + (f"; {', '.join(hidden)}'s lodThreshold1 past {'its' if len(hidden) == 1 else 'their'} farClip, so "
               "no screen draws it" if hidden else "")], added


def _lod_errors(spec) -> list[float] | None:
    """W39's stop for each of ``spec``'s LODs (:func:`write_lods`):
    ``error_px`` screen lines at the distance the game keeps its switch at
    (:func:`~azurik_mod.assets.lods.pixel_error`); ``None`` for none."""
    from azurkit.tools.characters import lods

    return None if spec.error_px is None else [lods.pixel_error(spec.error_px, d) for d in lods.thresholds(spec.at)]


def _lods_ahead(characters: bytes, body: str, spec) -> None:
    """W39's cuts of ``body``'s LOD 0 as a variant's W24, W29 and W30 leave
    it in ``characters``, started in a worker process while the build goes
    on (:func:`~azurik_mod.assets.decimate.chain_ahead`, as
    :func:`_shadow_ahead` starts W36's): W39 takes them if its LOD 0 is
    still this one.  Once a body, as there."""
    from azurkit.tools.characters import decimate
    from azurkit.tools.characters.body_codec import read_asset

    if spec.ratio and not decimate.ahead_of(characters):
        decimate.chain_ahead(read_asset(characters, body).lods[0], spec.ratio, _lod_errors(spec), source=characters)


def write_lods(game, engine, body: str, spec, vanilla: bytes | None = None) -> tuple[list[str], int]:
    """W39 (Step 2.166d, D537's L4): the body the player wears, ``body``,
    with a variant's LODs (``spec``, its recipe's ``lods``:
    :class:`~azurik_mod.patches._player_variants.Lods`): its LODs past
    LOD 0 cut anew from its final LOD 0, after every write of it (W24,
    W29, W30, W26, W31-W33), and before W36 and W38's copy, so the
    player's copy carries them
    (:func:`~azurik_mod.assets.decimate.screen_lods`; with
    ``spec.error_px`` LOD k stops that many screen lines off LOD k-1 at
    its switch distance, :func:`~azurik_mod.assets.lods.pixel_error`);
    garret4's ``lodThreshold1``-``4`` set to ``spec.at`` (any finite
    number, D23; a cell past its LODs to his ``farClip``, which the pick
    never reads: n = LODs - 1, 0x3EE73).  The realtime shadow draws LOD 1
    (:data:`~azurik_mod.assets.lods.SHADOW_LOD`), so W36 adds none; the
    body's other wearers (town_female_2 for female_2) switch at their own
    distances.  No ratio drops its LODs past LOD 0 (a one-LOD body is left
    as it is).  With no ``spec`` and ``vanilla`` (the image's
    characters.xbr, for a variant whose mesh edited LOD 0) a body with LODs
    of its own (catalisk's four, golem's four) has them cut anew from its
    edited LOD 0 at their vanilla shares of its triangles
    (:func:`~azurik_mod.assets.decimate.vanilla_shares`; D537's design
    0(b)), so its far LODs draw the edit too; every wearer's switch
    distances stay.  Its log line and the bytes its own runs grew by
    (below 0 for a drop)."""
    from azurkit.tools.characters import decimate, lods
    from azurkit.tools.characters.body_codec import read_asset
    from azurkit.tools.characters.model_inspect import MiB, own_runs

    characters = bytes(game["characters.xbr"])
    before = read_asset(characters, body).lods
    if spec is None:   # an edited body's own LODs at their vanilla shares
        ratios, errors = decimate.vanilla_shares(vanilla, body) if vanilla is not None else [], None
        if not ratios:
            return [], 0
    elif not spec.ratio and len(before) == 1:
        return [], 0
    else:
        ratios, errors = spec.ratio, _lod_errors(spec)
    worn = lods.wearers(bytes(engine.document.raw), body)
    grown, cuts = decimate.screen_lods(characters, body, ratios, errors)
    added = own_runs(grown, body)["bytes"] - own_runs(characters, body)["bytes"]
    game["characters.xbr"] = bytearray(grown)
    if not cuts:
        return [f"  Player model: {body}'s {len(before) - 1} LODs past LOD 0 dropped (W39), "
                f"{-added / MiB:.2f} MiB fewer own runs"], added
    if spec is None:
        return [f"  Player model: {body}'s {len(cuts)} LODs past LOD 0 cut anew from its edited LOD 0 at their "
                "vanilla shares (W39): "
                + ", ".join(f"LOD {k} {decimate.drawn(c)} triangles ({r:.3g} of LOD 0's)"
                            for k, (c, r) in enumerate(zip(cuts, ratios), 1))
                + f"; its wearers switch at their own distances; {added / MiB:+.2f} MiB own runs"], added
    far = next((w.far for w in worn if w.species == PLAYER), lods.FLT_MAX)
    for k in range(lods.PICKED):
        set_keyed_double(engine, PLAYER, f"lodThreshold{k + 1}", spec.at[k] if k < len(cuts) else far)

    def at(kept_: list[float]) -> str:
        return ", ".join("none" if t >= lods.FLT_MAX else f"{t:g}" for t in kept_[:len(cuts)])
    n0 = decimate.drawn(before[0])
    others = [f"{w.species} at its own {at(w.thresholds)} m" for w in worn if w.species != PLAYER]
    return [f"  Player model: {body}'s LODs (W39): "
            + ", ".join(f"LOD {k} {decimate.drawn(c)} of LOD 0's {n0} triangles" for k, c in enumerate(cuts, 1))
            + f" (cut at {', '.join(f'{r:g}' for r in spec.ratio)}"
            + (f" within {spec.error_px:g} px at each switch" if spec.error_px is not None else "")
            + f"), {PLAYER} switching at {', '.join(f'{d:g}' for d in spec.at)} m"
            + (f", {', '.join(others)}" if others else "")
            + f"; its realtime shadow draws LOD {lods.SHADOW_LOD}; {added / MiB:.2f} MiB more own runs"], added


def remeshes(variant) -> bool:
    """Whether ``variant``'s recipe writes its body's mesh or textures
    (W24's ``mesh``: its glTF edit and mesh ops; W29's ``jiggle``; W30's
    ``textures``), which P2 makes the player's alone (Step 2.203, D543)."""
    return variant is not None and (variant.mesh is not None or variant.jiggle is not None or bool(variant.textures))


def copy_alone(game, body: str) -> bool:
    """Whether the game loads W38's copy of ``body`` (``v/skin``) without
    the body (AZ-761, Step 2.198): no level of ``game``'s image places a
    critter wearing it (:func:`~azurik_mod.assets.model_inspect.placed_species`,
    the wearers its stored config.xbr names:
    :func:`~azurik_mod.assets.lods.wearers`), so only the player's copy
    loads: booblord's town_female_2 (D361; in xemu booblord_high_human's
    and booblord_human's upper heap held booblord_high's and booblord's
    runs to the byte, Step 2.166d's N1).  False where ``game`` reads no
    image."""
    from azurkit.tools.characters.lods import wearers
    from azurkit.tools.characters.model_inspect import placed_species

    iso = getattr(game, "root", None)
    if iso is None:
        return False
    return not {w.species.casefold() for w in wearers(game.stored("config.xbr"), body)} & placed_species(iso)


def _load_budget(game, body: str, who: str, sounds: bool, ram: int, shadow: int = 0, screen: int = 0,
                 alone: bool = False) -> list[str]:
    """The player's own load runs in the built files against the game's
    load budget (Step 2.158, D491; Step 2.158b, D509;
    :func:`~azurik_mod.assets.model_inspect.own_runs`), checked after
    every write to characters.xbr and fx.xbr: past the error line a
    :class:`ValueError` (the build writes nothing, D35: past it a1's save
    loses pieces of its inventory screen in play), past the warning line one
    log line, else none.  The lines are
    :func:`~azurik_mod.assets.model_inspect.lines_for` the budget the built
    default.xbe holds (Step 2.162b, D515: 40 MiB, or what
    ``qol_memory_budget`` wrote one layer before); a refusal that 42 MiB
    would let through names the pack.  ``ram`` (``--ram``, Step 2.162i,
    D576; 256, Step 2.162l, D600) takes the lines of the machine
    :func:`~azurik_mod.assets.model_inspect.lines_ram` finds that
    default.xbe built for (128 with both ``model_inspect.UPPER_PACKS``, 256
    with ``model_inspect.UPPER256_PACK`` too, applied one layer before),
    else the next lower one's; a refusal a larger machine's lines would let
    through names its ``--ram``.  With the 128 or 256 MiB lines, a body
    whose largest single run passes
    ``model_inspect.run_line_for`` is refused too, whatever its total, and
    one past a smaller machine's lines gets a log line saying where it
    plays right (D588: 128 is the default target).
    ``sounds``: the build appended sounds to fx.xbr (a variant's, the
    bare-hands kit's); ``shadow``: the bytes W36's shadow LOD added
    (:func:`write_shadow_lod`) and ``screen`` those W39's LODs added
    (:func:`write_lods`), each twice when W38 copies the body and the
    game loads both, each named in a refusal it alone causes; ``alone``
    (:func:`copy_alone`, AZ-761): the game loads W38's copy without the
    body, whose own entry then counts no runs."""
    from azurkit.tools.characters import model_inspect as mi

    xbe = bytes(game["default.xbe"])
    budget = mi.budget_of(xbe)
    tier = mi.lines_ram(xbe, ram)
    error, warning = mi.lines_for(budget, tier)
    own = mi.own_runs(bytes(game["characters.xbr"]), body, bytes(game["fx.xbr"]) if sounds else None,
                      body_entry=not alone)
    run = mi.run_line_for(budget, tier)
    machine = {128: f"a 128 MiB machine with {' and '.join(mi.UPPER_PACKS)}",
               256: f"a 256 MiB machine with {mi.UPPER256_PACK}"}
    up = next((r for r in mi.RAMS if r > tier and own["bytes"] <= mi.lines_for(budget, r)[0]
               and own["largest"] <= mi.run_line_for(budget, r)), None)
    hint_up = "" if up is None else (
        f", or build for a 128 MiB machine: --ram 128 with {' and '.join(mi.UPPER_PACKS)} on (line "
        f"{mi.lines_for(budget, 128)[0] / mi.MiB:g} MiB)" if up == 128 else
        f", or build for a 256 MiB machine: --ram 256 with {mi.UPPER256_PACK} on (line "
        f"{mi.lines_for(budget, 256)[0] / mi.MiB:g} MiB, one run {mi.run_line_for(budget, 256) / mi.MiB:.2f}; xemu "
        "v0.16.2 or later at mem_limit 256 only)")
    if own["bytes"] > error:
        raised = mi.lines_for(mi.ROOM, tier)[0]
        hint = (f", or set qol_memory_budget to {mi.ROOM // mi.MiB} MiB (line {raised / mi.MiB:g} MiB)"
                if budget < mi.ROOM and own["bytes"] <= raised else "")
        where = (f"{machine[tier]} leaves it at the game's {budget / mi.MiB:g} MiB budget" if tier >= 128 else
                 f"the game's {budget / mi.MiB:g} MiB budget leaves it beside a level loaded from a save and its menus")
        shed = (f', or "lods": {{"shadow": false}} (W36\'s shadow LOD added {shadow / mi.MiB:.2f} MiB)'
                if shadow and own["bytes"] - shadow <= error else "")
        shed += (f', or fewer "lods" (W39\'s LODs added {screen / mi.MiB:.2f} MiB)'
                 if screen > 0 and own["bytes"] - screen <= error else "")
        raise ValueError(f"--player-character {who!r}: its own load runs, {mi.own_words(own)}, pass the "
                         f"{error / mi.MiB:g} MiB {where}; "
                         f"make its mesh or clips smaller{hint}{hint_up}{shed}")
    if tier >= 128 and own["largest"] > run:
        seen = (f"at 42 MiB the largest that played, {mi.RUN_ERROR_256 / mi.MiB:.2f}; one of 128.90 MiB fits no tier "
                "of the heap and never loaded" if tier == 256 else
                f"at 42 MiB the largest that kept a1, w1 and e2 whole, {mi.RUN_ERROR_128 / mi.MiB:.2f}, went above "
                "64 MiB; one of 43.11 found no room there and never loaded")
        raise ValueError(f"--player-character {who!r}: its largest own load run, {own['largest'] / mi.MiB:.2f} MiB of "
                         f"{mi.own_words(own)}, passes the {run / mi.MiB:.2f} MiB one run may take on "
                         f"{machine[tier]} at the game's {budget / mi.MiB:g} MiB budget ({seen}); "
                         f"make its mesh smaller{hint_up}")
    said = []
    if own["bytes"] > warning:
        seen = {64: f"a1's save keeps its inventory screen whole in play with {mi.EDGES[0]} MiB at 40 MiB",
                128: f"at 128 MiB a body played whole with its mesh run above 64 MiB with {mi.EDGES_128[0]:.2f} MiB, "
                     f"and one of {mi.EDGES_128[1]:.2f} never finished loading",
                256: f"at 256 MiB a body held vanilla's frame rate with {mi.EDGES_256[0]:.2f} MiB, and one of "
                     f"{mi.EDGES_256[1]:.2f} played 34-36 % under it at w1 in real-time xemu"}[tier]
        said.append(f"  Player model budget: its own load runs {mi.own_words(own)}, past {warning / mi.MiB:g} MiB "
                    f"of the {budget / mi.MiB:g} MiB budget{f' on a {tier} MiB machine' if tier >= 128 else ''} "
                    f"({seen}, the build's limit {error / mi.MiB:g})")
    mid = mi.lines_for(budget, 128)[0]
    if tier == 256 and (own["bytes"] > mid or own["largest"] > mi.run_line_for(budget)):
        said.append(f"  Player model budget: its own load runs, {own['bytes'] / mi.MiB:.2f} MiB (its largest run "
                    f"{own['largest'] / mi.MiB:.2f}), pass the {mid / mi.MiB:g} MiB (one run "
                    f"{mi.run_line_for(budget) / mi.MiB:.2f}) a 128 MiB machine takes: this build plays right only on a "
                    "256 MiB one (xemu v0.16.2 or later at mem_limit 256); at 128 MiB it loses loads or never finishes "
                    "loading, and on a 64 MiB Xbox it loses pieces and textures or hangs loading (--ram 128 refuses "
                    "the body)")
    elif tier >= 128 and own["bytes"] > (low := mi.lines_for(budget, 64)[0]):
        on = ("128 or 256 MiB one (xemu at mem_limit 128 or 256)" if tier == 256 else
              "128 MiB one (xemu at mem_limit 128)")
        said.append(f"  Player model budget: its own load runs, {own['bytes'] / mi.MiB:.2f} MiB, pass the "
                    f"{low / mi.MiB:g} MiB a 64 MiB machine takes: this build plays right only on a {on}; on a 64 "
                    "MiB Xbox it loses pieces and textures, and a larger one hangs loading (xemu at 64; --ram 64 "
                    "refuses the body)")
    return said


__all__ = [
    "ARMOR_FX",
    "ATTACK_BOX_HOOK",
    "ATTACK_BOX_HOOK_VA",
    "ATTACK_BOX_SHIM",
    "ATTACK_BOX_SHIM_NAME",
    "ATTACK_BUMP",
    "ATTACK_BUMP_MASK",
    "ATTACK_DEFAULTS",
    "ATTACK_GROUND",
    "ATTACK_REACH",
    "ActionPoint",
    "Attack",
    "AttackLogic",
    "AttackMove",
    "Combo",
    "BALANCE_CAP",
    "BALANCE_FLOOR",
    "BUMP_BELOW",
    "CLIMB_HOOKS",
    "CLIMB_OFFSETS",
    "CLIMB_OFFSETS_HOOK",
    "CLIMB_SHIM",
    "CLIMB_SHIM_NAME",
    "CAMERA_RIG",
    "CARRY_COLUMNS",
    "CARRY_ENTRIES",
    "CARRY_HOOK",
    "CARRY_HOOK_VA",
    "CARRY_SHIM",
    "CARRY_SHIM_NAME",
    "CameraPlan",
    "CameraShape",
    "DAMAGE_PLUG",
    "DEFAULT_MODE",
    "DEFAULT_SIZE",
    "EYE_HOOK",
    "EYE_LAND",
    "EYE_HOOK_VA",
    "EYE_SHIM",
    "EYE_SHIM_NAME",
    "EYE_MARGINS",
    "FLYERS",
    "FX_DEFAULT_HOOK",
    "FX_DRAIN_AT",
    "FX_RING_AT",
    "FX_RING_HOOKS",
    "FX_RING_SHIM",
    "FX_RING_SHIM_NAME",
    "FX_RING_STATE",
    "FX_RING_TABLE",
    "FX_ROTATION_AT",
    "G4_ROLL",
    "HELD_COLUMNS",
    "HIT_DELAY_HOOK",
    "HIT_DELAY_HOOK_VA",
    "HIT_DELAY_SCALE",
    "HIT_DELAY_SHIM",
    "HIT_DELAY_SHIM_NAME",
    "HIT_FX_HOOK",
    "HIT_FX_HOOK_VA",
    "HIT_FX_SHIM",
    "THUD_HOOK",
    "THUD_HOOK_VA",
    "THUD_NAME",
    "THUD_SHIM",
    "THUD_SHIM_NAME",
    "TICK_EDGE",
    "HIT_FX_SHIM_NAME",
    "HIT_FLASH",
    "HIT_FX_NAME",
    "HIT_HOOK",
    "HIT_HOOK_VA",
    "HIT_SECONDS",
    "HIT_SHIM",
    "HIT_SHIM_NAME",
    "HIT_NEAR",
    "HIT_REACH",
    "JIGGLE_HOOK",
    "JIGGLE_HOOK_VA",
    "JIGGLE_SCENE",
    "JIGGLE_SHIM",
    "JIGGLE_SHIM_NAME",
    "JIGGLE_STRENGTH",
    "JIGGLE_TABLE",
    "JIGGLE_WORDS",
    "JIGGLE_X26",
    "HIT_TICKS",
    "JUMP_ATTACK",
    "MODES",
    "MODE_ANIMS",
    "MODE_GRADES",
    "MODE_NAMES",
    "MODE_SHARES",
    "MULTIPLIER",
    "NORM_RECORDS",
    "NO_CONTACT",
    "PLAYER",
    "PlayerModel",
    "QUIET_DIR",
    "RATE_MARGIN",
    "REACH_BUMP",
    "REFUSED",
    "RING_COLUMNS",
    "RING_ENTRY",
    "RING_SIZE",
    "ROLL_HOOK",
    "ROLL_HOOK_VA",
    "ROLL_SHIM",
    "ROLL_SHIM_NAME",
    "ROTATE_HOOK",
    "ROTATE_HOOK_VA",
    "ROTATE_SHIM",
    "ROTATE_SHIM_NAME",
    "SAME_BUILD",
    "SCRIPTED",
    "SELF_DIR",
    "SHIMS",
    "SHIM_HOOKS",
    "XBE_SITES",
    "HANDED_VAS",
    "SWIM_BOB",
    "SWIM_HOLDS",
    "SWIM_HOLD_DIR",
    "SWIM_HOLD_LENGTH",
    "SWIM_SLOT",
    "SURFACE_DIR",
    "SURFACE_EYE",
    "SURFACE_FLOOR",
    "SURFACE_MARKER",
    "SURFACE_SLOTS",
    "SIZES",
    "SizeShape",
    "Swing",
    "SLOW_BONUS",
    "SLOW_RATIO",
    "SPIN_CLIPS",
    "STAFF_NODE",
    "STAFF_SWEEP_GATE",
    "STAFF_SWEEP_MARKER",
    "STAFF_WALLS",
    "DIRECTION_EDITS",
    "BLAST_HOOK",
    "BLAST_HOOKS",
    "BLAST_HOLD_HOOK",
    "BLAST_LAND_HOOKS",
    "BLAST_SHIM",
    "install_air_blast_shim",
    "DRAIN_HOOKS",
    "drain_columns",
    "install_drain_shim",
    "CHAIN_GATES",
    "lift_chain_gates",
    "set_unstunned",
    "SETS_HOOKS",
    "attack_sets",
    "install_attack_sets_shim",
    "install_fx_default_shim",
    "player_fx_key",
    "set_lines",
    "STAFF_X1",
    "SUPPORT",
    "UNSEEN",
    "UNTESTED",
    "WALK_SPEED",
    "WINDUP_MAX",
    "WINGS_BIND",
    "WINGS_MARKER",
    "WINGS_POSE",
    "WINGS_SHIM",
    "WINGS_SHIM_NAME",
    "X3_CLOSES",
    "X3_HALF",
    "X3_OPENS",
    "X3_SAMPLES",
    "action_point",
    "apply_player_model",
    "at_point",
    "attack_move",
    "CENTRED_DIR",
    "attack_copies",
    "attacks",
    "bakes",
    "balance_factor",
    "body_height",
    "body_scale",
    "body_size",
    "can_hit",
    "camera_plan",
    "camera_shape",
    "carry_mask",
    "check_player_model",
    "copy_alone",
    "eye_height",
    "field_damage",
    "field_switches",
    "fill_mask",
    "fit_armor",
    "floats",
    "follow_hands",
    "hand_bones",
    "heavy_side",
    "held_swim",
    "hit_flash",
    "hit_fx_type",
    "hitting_ring",
    "install_attack_box_shim",
    "install_attack_carry_shim",
    "install_throw_shim",
    "install_climb_offsets",
    "install_camera_rig",
    "install_climb_shim",
    "install_over_top_shim",
    "install_stance_term_shim",
    "install_fade_shim",
    "install_near_draw_shim",
    "install_water_push_shim",
    "install_eye_shim",
    "install_fx_ring_shim",
    "install_jiggle_shim",
    "install_hit_delay_shim",
    "install_hit_fx_shim",
    "install_thud_shim",
    "install_hit_shim",
    "install_roll_shim",
    "install_rotate_shim",
    "install_sounds_shim",
    "install_staff_at_x1",
    "install_staff_walls_off",
    "install_wings_shim",
    "is_melee",
    "melee_reach",
    "mode_status",
    "model_sounds",
    "move_window",
    "movement_size",
    "needs_climb_offsets",
    "needs_climb_shim",
    "needs_damage_marker",
    "needs_wings_shim",
    "player_models",
    "projectile_row",
    "quiet_fills",
    "reach_misses",
    "remeshes",
    "rest_distance",
    "rotation",
    "self_drains",
    "sent_window",
    "shortens_hit_delay",
    "shot_timing",
    "shim_data",
    "size_scale",
    "size_shape",
    "source_clip",
    "staff_meshes",
    "staff_scales",
    "standard_rate",
    "status",
    "surfaced_swim",
    "substitutes",
    "scripted_switches",
    "sweeps_no_staff",
    "throw_bone",
    "swim_margins",
    "walk_words",
    "weigh_attacks",
    "windup",
    "write_shadow_lod",
    "write_walk_speed",
    "x3_anchor",
    "x3_columns",
    "x3_mask",
    "style_picks",
    "style_windows",
    "x3_rows",
]
