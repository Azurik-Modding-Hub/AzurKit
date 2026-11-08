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

**Moves:** `clips` makes clips by a generator (`{"spin": {"generator": "t_spin", "length": 0.4, "turns": 2}}`) or
reads a glTF's; `columns` gives an attack column (`basic1`, `finish`, `jump attack` …) a clip of its own or its base's;
`carry` lists columns that move with the stick and `held` those that chain while the button is held; `idles`
(`idle`, `idle_1`, `idle_2`, `wait`) and `slots` (`walk`, `run`, `walk_backwards`, `run_backwards`, `jump`,
`touchdown`, `victory_1`) name clips; `victory_cancel` ends a victory after that many seconds; `drain`
(`{"targets": "nearest"}` or `"all"`); `markers` grows hit markers on the body.

**Sounds:**
- `sounds`: `own` (the default) or `garret4` (Garret's every sound, his voice too).
- `voice`: `own` or `silent` (no hurt, death, idle or taunt voice; its WAVs still play).
- `wavs`: a WAV per role, a file a take (up to 20): `{"hurt": ["ow.wav", "oof.wav"]}`. The roles are `hurt`, `death`,
  `idle`, `taunt`, `land`, `roll`, `jump`, `footstep`, `fall` (a long fall's landing) and `climb` (a ledge or a
  ladder's top). A WAV is integer PCM of 8 to 32 bits, mono or stereo, at any rate.
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
(`{"hips": {"title": "Hips", "ops": ["pelvis"], "value": 1.2}}`); `jiggle` frees bones and hangs springs on them.

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
