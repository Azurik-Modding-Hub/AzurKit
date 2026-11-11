# Writing a variant

A variant is a recipe over one of the game's creatures: its body, size, moves, sounds, effects and looks, applied to
your own copy of the game. The Variants view (Characters › Variants) writes recipes for you; this page is for
authors who write or check one by hand, or share one as community content.

## The folder

- Your variant `name` is a folder `variants/<name>/` in AzurKit's data folder (or the folder `AZURKIT_VARIANTS`
  names; the web page keeps it in your browser). It holds `recipe.json`, `{"<name>": {the recipe}}`, and every file
  the recipe names, beside it: no absolute path and no `..`.
- A name is a lower-case letter, then lower-case letters, digits and `_`, and no species' or built-in variant's name.
- Export packs the folder as a zip, which Import takes back. Export names any file made from the game's own (a glTF
  of a game model holds its geometry): those belong to the game's rights holders, so keep them out of what you share
  unless the place allows game files.
- A community content repository lists a variant as an entry of kind `variant`: its recipe file and the files it
  names, each with its size and checksum.

## The rules

- Every field but `base` (or `from`) is optional. An unknown field or value is refused by name, and nothing is built.
- A number is any finite number. Nothing is clamped: a slider's range is only a hint.
- The recipe's checksum (the status line's `recipe …`) covers what builds, but not `title`, `notes`, `voice`,
  `wavs`, `sfx` or `shouts`.
- Check with game data dresses the recipe as a build would, so it shows the same refusals a build gives.

## The fields

**Labels:** `title` and `notes`, what the Models view shows.

**Body:**
- `base`: the species it is made on (`garret4` is Garret's own body).
- `mode`: `own` (Balanced: its own moves and attacks, evened) or `garret4` (Skin only: Garret's moves in its skin).
- `size`: `own` or `garret4` (Garret's height); `scale` multiplies it.
- `arms`: `{"out_deg": 4}` turns both arms out (negative turns them in); `clips` sets it a clip at a time.
- `rotate`: `true` plays its attack clips in turn on the basic attacks.

**Attacks:** `attacks` multiplies `reach`, `damage` and `speed`, and sets `balance`, `ground` and `through_walls`
(`true` or `false`); `weapon` names the weapon it wears (`default`, `own` or a weapon's name), which then plays every
attack column.

**Moves:** `clips` makes clips by a generator (`{"spin": {"generator": "t_spin", "length": 0.4, "turns": 2,
"active": [0.2, 0.8], "box": {"centre": [0, 0.5, 1.0], "half": [0.6, 0.6, 0.5]}}}`) or reads a glTF's; `columns` gives an attack column (`basic1`, `finish`, `jump attack` …) a clip of its own or its base's;
`carry` lists columns that move with the stick and `held` those that chain while the button is held; `idles`
(`idle`, `idle_1`, `idle_2`, `wait`) and `slots` (`walk`, `run`, `walk_backwards`, `run_backwards`, `jump`,
`touchdown`, `victory_1`) name clips; `victory_cancel` ends a victory after that many seconds; `drain`
(`{"targets": "nearest"}` or `"all"`); `markers` grows hit markers on the body.

**Sounds:**
- `sounds`: `own` (the default) or `garret4` (Garret's every sound, his voice too).
- `voice`: `own` or `silent` (no hurt, death, idle or taunt voice; its WAVs still play).
- `wavs`: a WAV per role, a file a take (up to 20): `{"hurt": ["ow.wav", "oof.wav"]}`. The roles are `hurt`, `death`,
  `idle`, `taunt`, `land`, `roll`, `jump`, `footstep`, `fall` (a long fall's landing) and `climb` (a ledge or a
  ladder's top). A WAV is integer PCM of 8 to 32 bits, mono or stereo, at 1 kHz or more.
- `sfx`: sounds made by a generator for attack columns: `{"whip": {"generator": "whoosh", "length": 0.8, "swells": 4,
  "seed": 5, "columns": ["basic1"]}}` (`takes`, how many, defaults to 1), or `"generator": "wav"` with `files`.
- `shouts`: `{"files": [...]}`, its voice where Garret shouts under another weapon.
- `voice`, `wavs`, `sfx` and `shouts` need `sounds` `own`, and a base with sounds of its own (Balthazar, Keylord …)
  takes none of them: the Sounds tab says so.

**Effects:**
- `effects`: rows, each a `template` played on its `columns`:
  `{"template": "fireball", "columns": ["basic3"], "colour": [1, 0.45, 0.1], "speed": 18, "seek": true}`.
  The templates are the projectiles `fireball`, `ice_shard` and `arrow` (one a build, and none where the base's
  bare hands already throw, in `own` mode), the shields `bubble`, `dome` and `barrier`, and the beams `stream`,
  `bolts` and `laser` (three shields and beams at most). A row may set its `colour` (red, green and blue, 1 full) and
  any of its template's numbers (the Effects tab lists them with their defaults); a beam's `range` may be `"auto"`, its
  column's reach; a projectile's `seek` aims each throw at the nearest critter ahead.
- `fx`, `fx_grafts` and `fx_ring` edit the body's own effects graph record by record, graft others onto it and set
  the ring that plays shields and beams (`false` turns it off). They are expert fields: copy Beamlord's.

**Shape:** `mesh` sculpts the body (`ops`: `scale`, `push`, `taper`, `tuck` …) or takes an edited glTF of it
(`{"gltf": {"file": "body.glb", "sha256": "…"}}`); `shapes` names sliders over its ops
(`{"hips": {"title": "Hips", "ops": ["pelvis"], "value": 1.2}}`); `jiggle` frees bones and hangs springs on them;
`places` (New from this writes it) hangs them where another body's build does.

**Looks:** `colours` recolours its material rows (`[{"row": 0, "ops": [...]}]`, or an edited PNG of a row); `textures`
paints new ones through its mesh; `texture_scale` sizes them; `lods` sets its detail levels and shadow.

**From another:** `"from": "booblord"` (or a list) takes that recipe's every field but its labels, and lays over it
only its own `title`, `notes`, `effects`, `colours`, `shapes` values, `jiggle` and `texture_scale`, and adds
`mesh_ops` and `texture_ops` after that recipe's.

## An example

```json
{"lady": {"title": "Lady", "base": "town_female_2", "mode": "own", "scale": 1.1,
          "voice": "silent", "wavs": {"hurt": ["ow.wav"]},
          "effects": [{"template": "bubble", "columns": ["basic2"], "colour": [1, 0.4, 0.8]}]}}
```

saved as `variants/lady/recipe.json`, with `ow.wav` beside it.

## Field reference

Every field a recipe may hold, as the loader checks it (`src/azurkit/tools/characters/_player_variants.py`). A
build checks the rest against the game's data: a bone, mesh group, clip or column the body lacks is refused by name
then. Lengths are model units (about a metre), in the body's frame: x right, y forward, z up.

```json
{"<name>": {"title": "...", "notes": "...", "base": "<species>",
  "mode": "own", "size": "own", "scale": 1.0, "sounds": "own",
  "attacks": {"reach": 1.0, "damage": 1.0, "speed": 1.0, "balance": true, "ground": true,
              "through_walls": false},
  "markers": ["m_damage"],
  "clips": {"<clip>": {"generator": "<t_spin|...>", "...": "its parameters"}},
  "columns": {"<attacks_anims column>": "<clip of the recipe, or of the base>"},
  "carry": ["<column>"], "held": ["<column>"], "rotate": false,
  "idles": {"idle": "<clip of the recipe, or of the base>", "idle_1": "<clip>", "wait": [10.0, 10.0]},
  "slots": {"walk": "<clip>", "walk_backwards": "<clip>", "run": "<clip>", "run_backwards": "<clip>",
            "victory_1": "<clip>", "jump": "<clip>", "touchdown": "<clip>"},
  "victory_cancel": 0.5, "drain": {"targets": "nearest"},
  "fx": [{"record": 17, "name": "<its name>", "type": "<its node type>", "set": {"<attribute>": 1.0},
          "texture": {"recolor": {"ramp": [[0, 0, 0], [0.4, 0.7, 1.0]], "gamma": 1.0}}}],
  "fx_grafts": [{"template": "electric_shield", "parent": 5}],
  "effects": [{"template": "fireball", "columns": ["basic3", "finish"], "colour": [1, 0.45, 0.1], "speed": 18,
               "arc": 0.2, "size": 0.12, "radius": 0.4, "life": 2},
              {"template": "bubble", "columns": ["basic1"], "colour": [0.3, 0.6, 1], "opacity": 0.35, "fade": 0.3},
              {"template": "laser", "columns": ["basic2"], "colour": [1, 0.1, 0.1], "width": 0.2, "range": "auto"}],
  "voice": "own", "wavs": {"hurt": ["ow.wav"]},
  "sfx": {"<sound>": {"generator": "whoosh", "length": 0.4, "swells": 4, "seed": 1, "takes": 3,
                      "columns": ["<attacks_anims column>"]}},
  "mesh": {"gltf": {"file": "<edit.glb beside the recipe>", "sha256": "<64 hex>"},
           "keep": ["<bone>"],
           "ops": [{"op": "scale", "bone": "<bone>", "offset": [0, 0, 0], "radius": [0.1, 0.1, 0.1],
                    "factors": [1.5, 1.5, 1.5], "mirror": true, "only": ["<bone>"], "profile": "smooth"},
                   {"op": "push", "name": "<label>", "bone": "<bone>", "offset": [0, 0, 0], "dir": [0, 1, 0],
                    "height": 0.1, "radius": {"in": 0.1, "out": 0.1, "up": 0.1, "down": 0.1}, "depth": 0.1,
                    "fold": 1.0, "groups": [1], "mirror": true},
                   {"op": "taper", "bone": "<bone>", "factors": [0.9, 0.9], "plateau": 0.05, "half": 0.1,
                    "reach": [0.2, 0.3]},
                   {"op": "tuck", "groups": [1], "under": [4], "dir": [0, 1, 0], "margin": 0.003,
                    "window": 0.05, "skip": ["<bone>"], "strict": true, "band": [1.2, 1.3], "faces": true}]},
  "shapes": {"<shape>": {"title": "<its slider's title>", "ops": ["<a round or scale op's name>"], "value": 1.0}},
  "arms": {"out_deg": 4.0},
  "jiggle": {"frees": [{"group": 1, "bone": "<leaf>", "into": "<its parent>"}, {"group": 4, "bone": "<bone>", "drop": true}],
             "bones": [{"role": "<name>", "bone": "<leaf bone>", "parent": "<bone>", "shape": ["<push op name>"],
                        "groups": [1, 4], "takes": ["<bone>"], "weight": 0.9,
                        "spring": {"freq": 2.6, "damping": 0.13, "travel": [0.05, 0.06, 0.12],
                                   "weights": [0.65, 0.42, 1.0], "gain": 2.3, "gravity": 1.0, "give": 0.07,
                                   "accel": 7.0, "pace": 3.0, "turn": 0.3, "rot_share": 0.65, "sides": "auto",
                                   "centre": "auto", "pivot": [0, -0.07, 0], "swim": [0.15, 3.0]}},
                       {"role": "<name>", "bone": "<leaf bone>", "parent": "<bone>", "shape": ["<push op name>"],
                        "groups": [1], "takes": ["<bone>"], "weight": 0.75, "freq": 1.6, "damping": 0.3,
                        "travel": 0.045, "turn": 0.35, "hang": 0.5, "gain": 2.2, "drive": 6.5}],
             "springs": [{"role": "<name>", "bone": "<a bone of the body>", "parent": "<its parent>",
                          "spring": {"freq": 1.8, "damping": 0.2, "travel": 0.05}}],
             "keys": 15, "still": ["<clip>"], "loops": ["<clip>"]},
  "colours": [{"ops": [{"op": "hsv", "hue": -100, "window": [195, 238]}]}],
  "lods": {"shadow": false}}}
```

### Body and gameplay

- `base`: the species it is made on. `garret4` builds on Garret's own body and build: there `mode` `garret4`,
  `size` `garret4`, `sounds` `garret4` and `fx_ring` are refused (they mean nothing on him), his own rows are
  recoloured in place and his `scale` and `attacks` numbers are his own sliders'. `{"garret_green": {"base":
  "garret4", "colours": [{"ops": [{"op": "hsv", "hue": -100, "window": [195, 238]}]}]}}` turns his blues green, the
  window ending below his hair's purples (from about 246 degrees).
- `mode`: `own` (the default: its own moves and attacks, evened) or `garret4` (Garret's exact moves in its skin).
  `garret4` takes no `clips`, `markers`, `carry`, `held`, `idles` or `slots`: Garret's box and timing play every
  column there. `full` is retired: use `own`.
- `size`: `own` (the default) or `garret4` (Garret's height); `scale` multiplies it (any finite number).
- `attacks`: `reach`, `damage` and `speed` multiply the attacks (any finite number); `balance` and `ground` (true or
  false) override the mode's own default; `through_walls` true lets the player's hits reach a critter behind a wall
  or door (switches, crystals and puzzles are unchanged).
- `weapon`: `default`, `own` or a weapon's name (lower-case letters, digits and `_`; the build checks it). A weapon
  plays every attack column, so a recipe with one names no `clips`, `columns`, `carry` or `held`, unless they are a
  moveset weapon's (Booblord's spins).
- `markers`: marker names (`m_damage` …) grown on the body, as `marker_source`'s (default `garret4`) records.

### Moves

- `clips`: `{name: {"generator": G, ...}}`, a name lower-case letters, digits and `_`; each made at build time and
  stored under the body as `v/<name>`, which only a column or slot that names it plays. Any clip may take `"seek":
  true` (each column playing it turns to its target at the attack's start). The generators and the keys each needs:
  - `t_spin` (`length` s, `turns`, `active` [on, off] shares of the clip, `box` {`centre`, `half`}; `hop`): the
    body spinning about its root;
  - `hand_spin` (`length`, `turns`, `tilt_deg` (0, 90], `hand`, `hand_z`, `plant`, `active`, `box`; `hold`): a
    spin on one hand;
  - `beam` (`source`, `length`, `switch`, `aim`, `level_deg`, `box` {`from`, `to`, `half_width`, `z`}) and `nova`
    (`source`, `length`, `switch`, `aim`, `spin_deg`, `box` {`half`, `centre_z`, `grow_from`, `grow_until`}),
    each with `sweep_deg`, `switch_z` or `switch_from` if wanted: a clip of the base's (`source`) as a line of
    lightning ahead or a growing ball (Beamlord's);
  - `gust` (`source`, `length`, `release`, `arrive`, `from`, `to`, `half`, `centre_z`, `cloud`, `cloud_scale`;
    `funnel` {`marker`, `size`}) and `air_blast` (`source`, `length`, `switch`, `aim`, `impact`, `bolt` {`from`,
    `half`, `centre_z`, `switch_z`, `hands`, `emitter`, `pitch_deg`}, `blast` {`half`, `centre_z`, `grow_from`,
    `grow_until`, `until`, `dome_unit`}): a wind and a blast as the air elemental's own build makes them;
  - `gltf` (`file`, `sha256`, `animation`; `active` [on, off] in clip seconds and `box` {`centre`, `half`}
    together, `rate`): an animation of a glTF beside the recipe, the root travelling no more than 10 % of the
    body's height;
  - `bake` (`body`, `clip`; `variant`): another humanoid body's clip (Garret's, a townsman's) baked onto this one.
- `columns`: `{column: clip}`, a recipe clip or one of the base's. The columns are `basic1`-`basic3`, `finish`,
  `finish2`, `finish3`, `sweep1`, `sweep2`, `sweep ledge`, `elemental1`-`elemental3`, `hose_attack_3`, `jump
  attack`, `right1`, `right2`, `left1`, `left2`, `back1`, `back2`, `up1`, `up2` and `down`; `roll forward` always
  keeps Garret's roll. A column it doesn't name keeps the swap's own pick.
- `carry`: columns that move with the stick; `held`: columns that chain while the button is held (never the roll).
- `rotate`: true plays the body's other attack clips in turn after the combo.
- `idles`: `idle` (the base, which loops while it stands), `idle_1`-`idle_6` (each played once, as a fidget),
  filled from `idle` on with no gap, and `wait` [low, high], the seconds of standing before a fidget (default
  [10, 10]; under 10 acts as 10). The base must end where it starts. Own mode only.
- `slots`: `walk`, `run`, `walk_backwards`, `run_backwards` (named with its forward twin, or neither),
  `victory_1`-`victory_6`, `jump`, `jump_standing`, `superjump`, `climb_drop` and `touchdown`, each a clip. A gait
  clip loops, so it ends where it starts, and its planted feet must move; a victory clip may not deal damage. Own
  mode only.
- `victory_cancel`: seconds after which a push of the stick ends a victory (left out, it plays whole).
- `drain`: `{"targets": "nearest"}` (the default) or `"all"`: whom a column playing the base's own life drain
  takes life from.

### Sounds

- `sounds`: `own` (the default) or `garret4`. `voice`, `wavs`, `sfx` and `shouts` need `own`, and a base with sounds
  of its own takes none of them (the build says so).
- `voice`: `own` or `silent`.
- `wavs`: `{role: [file, ...]}`, 1 to 20 files a role, each a `.wav` name with no folder, beside the recipe. Roles:
  `hurt`, `death`, `idle`, `taunt`, `land`, `roll`, `jump`, `footstep`, `fall`, `climb`.
- `sfx`: `{name: {...}}`, a name lower-case letters, digits and `_`, not a role, not `shout` and not ending in `_a`
  to `_s` (the game reads those as takes): `{"generator": "whoosh", "length" (s, at most 60), "swells", "seed",
  "columns"; "takes" 1-20}`, or `{"generator": "wav", "files", "columns"}`; `columns` the attack columns it plays on.
- `shouts`: `{"files": [...]}`, 1 to 20 WAVs: its voice where Garret shouts under another weapon.

### Effects

- `effects`: rows `{"template", "columns"; "colour", "seek", and any of the template's numbers}`. The projectiles
  `fireball`, `ice_shard` and `arrow` (`speed`, `arc`, `size`, `radius`, `life`; one projectile a build; only they
  take `seek`), the shields `bubble` and `dome` (`size`, `opacity`, `fade`) and `barrier` (`size`, `ahead`,
  `fade`), and the beams `stream`, `bolts` and `laser` (`width`, `range`, which may be `"auto"`, `fade`): three
  shields and beams at most, a column in one row, never the roll. `colour` is red, green and blue, 1 full.
- `fx`: edits of the body's own effects graph, each naming a record by `record` (its index), `name` and `type`, and
  any of `set` (attributes by name), `links`, `inherit`, `material` (`opacity`, `alpha_ref`, `blend`), `parent`,
  `texture` (`recolor`, `png`, `stage`, `format`), `anchor` (a marker it binds to) and `mesh` (a static `.glb`).
  `python -m devkit models fx show` prints a graph's records.
- `fx_grafts`: `{"template": NAME, "parent": record}` (a named graft: `python -m devkit models fx templates`), or
  `{"from": {"archive", "key", "records"}, "parent"}`.
- `fx_ring`: `false` turns the ring that plays shields and beams off; else `slots` (1-12 copies), `arm` and `stand`
  (`key`, `trigger`, `hold` 0-65.535 s; `slots` 1-5, `fx`). Expert fields: copy Beamlord's.

### Shape

- `mesh`: `gltf` {`file`, `sha256`; `import` `positions` (the default), `topology` or `weights`} (an edited copy of
  `model export`'s file, yours only: a built-in takes none), `keep` (bones no op moves), `ops` and `drop`. At least
  one of `gltf`, `ops` or `drop`. The glTF's positions come first, then the ops. Each op is centred on its `bone`'s
  rest origin plus `offset`, and most take `mirror` (both sides), `only` (bones), `groups` (mesh groups) and `name`
  (what `shapes` and `jiggle` refer to). The ops and the keys each needs:
  - `scale` (`bone`, `radius`, `factors`; `profile`, `late`): scales inside an ellipsoid, full at its centre,
    fading to its edge;
  - `push` (`bone`, `dir`, `height`, `radius` {`in`, `out`, `up`, `down`}, `depth`; `fold`, `region`): a bump along
    `dir`;
  - `taper` (`bone`, `factors`, `plateau`, `half`, `reach`): x and y drawn in about a vertical line;
  - `tuck` (`groups`, `under`, `dir`, `margin`; `window`, `skip`, `strict`, `band`, `faces`): a layer a field op
    moved through the cloth `under` it moved back behind it;
  - `round` (`bone`, `radius`, `origin`, `blend`; `dir`, `gate`, `drape`, `bridge`, `beneath`, `pair`, `midline`,
    `behind`, `window`): a rounded form grown along a direction and blended in;
  - `subdivide` (`bone`, `radius`, `edge`; `smooth`, `apart`, `normals`): triangles split until no edge is longer
    than `edge`;
  - `thicken` (`bone`, `radius`, `depth`; `taper`): a two-sided layer (a sash) given thickness;
  - `hem` (`bone`, `radius`, `edge`, `groups`; `relax`, `inset`, `width`): a layer's open edges split and hemmed
    (`relax` at most 100 passes);
  - `relax` (`bone`, `radius`, `passes`; `open`): the surface smoothed (at most 100 passes);
  - `bind` (`bone`, `radius`, `groups`, `to`; `reach`, `fade`, `near`): a layer's skin weights taken from the
    nearest vertex of the `to` groups;
  - `reweight` (`bone`, `radius`, `take`, `into`, `share`; `z`, `x`): a share of the weight on `take` moved onto
    `into`;
  - `unwrap` (`bone`, `radius`; `shrink`), `island` (`bone`, `radius`, `rects`, `groups`; `uv`) and `atlas`
    (`groups`, `rect`): UVs laid anew, which the material's texture then needs repainted (`textures`);
  - `tube` (`bone`, `path`, `radius`, `group`, `rect`; `sides`, `rings`, `flat`, `across`, `closed`, `follow`,
    `segments`, `fade`, `reach`, `facets`, `smooth`, `under`, `skip`, `hang`): a new tube along a path (a
    ponytail), of at most 256 sides, 512 rings, (sides + 1) x rings 32,768 points and as many segments as rings;
  - `cut` (`bone`, `normal`, `radius`, `groups`; `under`, `press`, `trim`, `uv`, `snap`, `corner`): the mesh cut
    across a plane.
- `shapes`: `{name: {"title", "ops"; "below", "value", "turns"}}`, a slider each, sizing the `round` and `scale`
  ops it names (an op by one shape; `below` ops only under 1) by `value` (above 0, 1 by default); `turns`
  `[{"bone", "axis", "deg"}]` turn a bone `deg` times (value - 1) above 1. A build's character sizes them too:
  `{"species": "<name>", "shapes": {"<shape>": 1.2}}`. Needs a `mesh`.
- `arms`: `{"out_deg": D}` turns both arms out (negative: in) in every clip but the recipe's own; `"clips": {clip:
  D}` gives a clip its own. `poses`: `[{"clip", "bone", "axis", "deg", "window" [from, to] within 0-1; "ease"}]`
  turns a bone over part of a clip.
- `jiggle` (needs a `mesh`): `frees` (`{"group", "bone", and "into" its parent or "drop": true}`) and `bones`
  (at least one), new bones swung by springs: each `role`, `bone`, `parent`, `shape` (push op names), `groups`,
  `takes`, `weight`, and either `spring` (the game's real-time spring: `damping` and `travel`, `freq` Hz or
  `stiffness` N/m with `mass` kg, and any of `weights`, `gain`, `gravity`, `turn`, `rot_share`, `sides`,
  `centre`, `pivot`, `give`, `accel`, `swim`, `pace`, `squash`, `kick`, `kick_hold`, `kick_time`, `impact`,
  `wall`), the baked fields `freq`, `damping`, `travel`, `turn` (and `hang`, `gain`, `drive`), or `"keyed": true`
  (only the recipe's own clips move it). `springs` hangs real-time springs on the body's own bones (hair, cloth:
  `python -m devkit models model chains BODY` prints a starting set), 32 rows in all; `keys`, `still`, `loops` and
  `clear` tune the baked swing. A recipe with a `jiggle` takes none of its body's own hair springs.
- `places` (needs a `jiggle`): `{"of": NAME, "mesh": M, "jiggle": J}`, the `mesh` and `jiggle` whose build places
  the recipe's jiggle bones, each checked as a recipe's is. New from this writes it on its own copy of a built-in
  whose build places its springs by the recipe it is `from` (booblord_high: booblord's), so the copy's springs sit
  where the built-in's do and its clips' rests hold; `of` names that recipe. A recipe `from` the copy keeps it.

### Looks

- `colours`: `[{"row"?, "ops"}]`, one entry for every row (no `row`) and one a row, each row once: `hsv` (`hue`
  degrees added, `sat` and `value` times their own; `window` [lo, hi] hue degrees, `soft`, `spread`, `sat_min`,
  `value_min`), `swap` (`from`, `to` RGB 0-1, `reach`; never from a grey) or `png` (`file`, `sha256`: an edited PNG
  of that row's texture at its own size, first in an entry naming its row). Made in the player's copy of the body,
  so the creatures wearing it keep theirs.
- `textures` (needs a `mesh`): `[{"row", "size" (a power of two, 4-4096); "format" (`dxt1`, the default, `dxt3`,
  `bgra8`), "ops"}]`, each row once, painted through the mesh by `skin`, `shade`, `metal`, `strands`, `fill` and
  `sharpen` ops over a region (`bone`, `offset`, `radius`, `mirror`, `only`, `groups`, `z`, `feather`, `uv`).
- `texture_scale` (needs a `mesh`): a power of two, every texture baked that many times its size (1 by default).
- `lods`: `{"shadow": true, false or a share}` (a coarse LOD only the player's shadow draws), or `{"ratio": [up to
  4 shares in (0, 1]], "at": [a switch distance in m each], "error_px": p}` (the LODs cut anew from the edited
  body; `"ratio": []` drops them), not both. Both are cut from the recipe's `mesh`, so need one (`"shadow": false`
  doesn't).

### From another

`"from": NAME` (or a list of recipes each from the same one) names another recipe of the file, or a built-in. It
takes that recipe's fields but `title` and `notes`, and lays over them only its own `title`, `notes`,
`texture_scale`, `effects`, `colours`, `shapes` values and a whole `jiggle`, and adds its `mesh_ops` (`subdivide`
and `thicken` ops, and `{"over": NAME, "sides", "rings"}` laid over that recipe's `tube` of that name) after that
recipe's `mesh` ops and its `texture_ops` (`{"row", "ops"}`) after that recipe's ops of the row. Any other field is
refused by name. Its sounds, clip files and effects files are read from that recipe's folder.
