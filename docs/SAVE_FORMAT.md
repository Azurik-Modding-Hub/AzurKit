# Azurik save-file format

> **Status**: verified against a real save extracted from an
> `xbox_hdd.qcow2` xemu HDD image.  Directory layout, Xbox container
> files, and `.sav` file variants all decoded; per-file payload
> field structure is partially decoded (text saves' lines, a level
> save's record count) — full record-by-record decoders for `inv.sav`,
> `shared.sav`, and level saves remain future work.
>
> **Python module**: [`azurkit.tools.saves`](../src/azurkit/tools/saves/)
> **CLI**: `azurkit save inspect FOLDER|FILE.sav|HDD` and `azurkit save edit` (§ 6, § 7)
>
> Ported from Azurik_Modkit's `docs/`, where the format was decoded; its
> code is AzurKit's `src/azurkit/tools/saves/` (§ 8).

---

## 1. Directory layout

A single save slot lives in its own folder on the Xbox HDD.
Example (extracted from a real xemu save):

```
UDATA\4d530007\<save_id>\
    SaveMeta.xbx            76 B    Xbox-standard save metadata
    TitleMeta.xbx           38 B    Title-level metadata
    SaveImage.xbx         4096 B    64×64 ARGB thumbnail
    TitleImage.xbx       10240 B    Title icon
    signature.sav           20 B    HMAC-SHA1 digest (integrity check, § 7)

    inv.sav              16384 B    Binary: inventory (v7)
    loc.sav              16384 B    Text:   current location
    magic.sav            16384 B    Text:   spell / power stats
    shared.sav           16384 B    Binary: cross-level flags (v1)

    largeimage.xbx       34816 B    Bigger thumbnail (extra file)

    levels/
      air/
        a1.sav           16384 B    One per visited air level
        a3.sav  ...
      death/
        d1.sav  ...
      earth/
        e2.sav  ...
      fire/
        f1.sav  ...
      water/
        w1.sav           9316 B     Visited — non-zero
        w2.sav ...
      life.sav           16384 B
      selector.sav       16384 B
      town.sav           16384 B
      training_room.sav    992 B

TDATA\4d530007\
    options.sav             23 B    Title-level settings (CRLF text; see § 4a)
```

`4d530007` is Azurik's title ID (hex).  The inner UUID-like folder
(`5C0A938BD9AC` in the real save we inspected) is a random save-slot
ID generated per-save.

### Retail Xbox vs xemu HDD addressing

The runtime path is `\Device\Harddisk0\partition1\UDATA\<title>\...`
which maps to the Xbox E:\ drive.  On xemu's `xbox_hdd.qcow2` this
partition starts at a fixed byte offset inside the qcow2 image.
Empirically (from one xemu-created 8 GB HDD image):

| Partition offset | Size | Content |
|------------------|------|---------|
| `0x00080000` | 750 MB | CACHE0 (X:\) |
| `0x2EE80000` | 750 MB | CACHE1 (Y:\) |
| `0x5DC80000` | 750 MB | CACHE2 (Z:\) — game data cache |
| `0x8CA80000` | 500 MB | SYSTEM / dashboard |
| `0xABE80000` | 5.4 GB | **E:\ — retail save area** |

Inside the E:\ FATX partition:
- FAT starts at offset `0x1000` within the partition.
- Data area starts at the first cluster boundary after the FAT.
  On the xemu image we inspected this lands at partition offset
  `0x133000`, where the ROOT directory lives (cluster 1).
- Cluster size is 16 KB (32 × 512-byte sectors).
- FAT entries are 32-bit.

## 2. Extracting save data

xemu's built-in HDD export is the path of least resistance:

1. Run the game in xemu until it writes a save.
2. **Machine → Settings → System → HDD → Browse**.
3. Navigate to `UDATA\<azurik_title_id>\` and right-click → **Export**.
4. xemu drops the container files into a loose folder.
5. `azurkit save inspect <exported_folder>` for a summary.

The partition/FATX numbers above were first recovered with throwaway
qcow2 + FATX walkers; AzurKit's own reader is
`src/azurkit/tools/saves/fatx.py`, so `azurkit save inspect
xbox_hdd.qcow2` (or a raw image) lists the slots with no export.

## 3. Xbox-standard container files

Fully decoded.  The file layouts below are the same across every
Xbox title — Azurik doesn't customise them.

### 3a. SaveMeta.xbx / TitleMeta.xbx

A UTF-16-LE BOM (`FF FE`) followed by UTF-16-LE key/value pairs
separated by `\r\n` (`0D 00 0A 00`).  Some entries carry a
`\r\n\0\0` double terminator instead.  Optionally followed by a
binary tail that titles use for additional metadata (timestamps,
Xbox Live identifiers, etc.).

```
FF FE
Name=<save display name>\r\n
TitleName=Azurik: Rise of Perathia\r\n
NoCopy=1\r\n
<optional binary tail>
```

Python API (`saves.Meta`, in `container.py`): `Meta.from_bytes()`,
`get(key)`, `fields` (each `[key, value, line ending]`), `tail` (the
bytes after the last line), `bom`, `to_bytes()`.  Round-trip is
byte-identical when no field is changed: each line keeps its own
ending (a `\r\n\0\0` too), and `from_bytes` keeps the BOM off the
first key (`bom=True`) and `to_bytes` writes it back, so `get("Name")`
works on real files (AZ-122).  `saves.decode` gives a slot's top-level
meta file as its `fields` and its tail's length.

### 3b. SaveImage.xbx / TitleImage.xbx

Raw Xbox-swizzled ARGB raster data.  Exposed as opaque bytes;
decoding Xbox texture swizzle is out of scope (standard routines
exist in Cxbx-Reloaded, XGCore, etc.).

## 4. Azurik `.sav` file variants

Unlike the initial scaffold assumed, there is **no single 20-byte
header** across all `.sav` files.  The format splits into four
shapes, which `saves.decode` names by each file's `kind` (`text`,
`binary` or `signature`; a level save is `binary`):

### 4a. Text saves (`loc.sav`, `magic.sav`, `options.sav`)

latin-1 (8-bit clean), line-delimited.  In `loc.sav` / `magic.sav`
the header is literally the string `fileversion=<N>\n`, followed by
value lines (`key=value` OR bare numeric/path tokens), optionally
followed by a binary tail starting at the first `\x00` byte.  The latin-1 (rather than ascii)
decode is what makes edit → `to_bytes()` byte-lossless for saves
containing high bytes: an ascii/replace decode would turn them into
U+FFFD, which `to_bytes()` could no longer re-encode.

Real example (the start of `loc.sav`; the binary tail is elided):

```
fileversion=1\nlevels/death/d2\n\x00<binary tail>...
```

`magic.sav` holds exactly five values after its header, then zeros
to 16,384 B (AZ-276: until Step 2.20h this section showed six):

```
fileversion=1\n<f>\n<f>\n<d>\n<d>\n<f>\n\x00<zeros>...
```

| Line | Format | What it holds (`armor_mgr` field) |
|------|--------|-----------------------------------|
| 0 | `%f` | +0x54, the first `fx_magic_timer` slot |
| 1 | `%f` | +0x5C, the second |
| 2 | `%d` | +0x1C, the staff's element mask |
| 3 | `%d` | +0x2C, the armor's element mask |
| 4 | `%f` | +0x24, the armor gauge |

[verified xemu 2026-10-11, the agent sitting rz-a: every `magic.sav`
it decoded, four captures from two slots, has exactly these five
lines, 45–46 B of text; the formats and fields: static, the writer
`0x83230`, in the randomizer plan's RAM recipes § 6.]  The writer
refreshes line 0 as it writes: a poked 0.25 was saved as 1.0
[verified xemu, placed, rz-a].

`options.sav` has **no header**: it is three CRLF-delimited lines
of printable ASCII (`0.333333\r\n0.333333\r\n0\r\n` in the real
save).  `container.is_text` takes any file of printable ASCII lines
(LF or CRLF) that ends in a newline for a text save too, and
`Text.from_bytes` reads it with `version=None` and
`newline="\r\n"`, so `to_bytes()` re-emits it with no header and
CRLF line endings (Modkit read it as binary until its Step 1.33, its
ASCII digits taken for a u32 header).

Python API (`saves.Text`, in `container.py`): `Text.from_bytes()`,
`version` (None when headerless), `lines`, `tail` (the bytes from
the first NUL: `loc.sav`'s binary tail, or the padding), `newline`,
`final_newline`, `to_bytes()`.  Editing `lines` then calling
`to_bytes()` re-emits the file with the same header, line ending and
tail.  `saves.edit` does that for a slot, every edit or none (§ 5),
and `azurkit save edit FOLDER --set magic.sav:4=<value>`, with § 7's
flags, changes line 4, the armor gauge, and signs the slot again
(§ 4c).  What an edited
value does in game is not measured.

### 4b. Binary saves (`inv.sav`, `shared.sav`, level saves)

Each starts with a u32 `version`.  The u32 after it means something
different in each file, and only a level save's is a count (AZ-275).
From real samples:

| File | Version | The u32 at +4 | Body size (after +8) |
|------|---------|---------------|-----------|
| `inv.sav`         | 7 | the inventory's first field, an f32: 0x3F0AE72C, about 0.5426 | 16376 B |
| `shared.sav`      | 1 | the first entry's name length: 24 | 16376 B |
| `d2.sav` (visited) | 2 | P = 201 records | 12248 B |
| `w1.sav` (visited) | 2 | P = 153 records | 9308 B |
| `a1.sav` (not visited) | 0 | 0 | 16376 B all zero |
| `e5.sav` (not visited, large) | 0 | 0 | 32760 B all zero |

- **`inv.sav`** is the u32 7, then the 0x1D4 (468) bytes of the
  in-memory inventory as they are in RAM (layout: § 4e), then zeros
  to 16,384 B [verified xemu 2026-10-11, the agent sitting rz-a:
  bytes 4–472 equal the inventory in RAM at the writer `0x58B50` and
  after the reader on a reload].  The f32 at +4 is the inventory's
  first field, from which the gameState values `current day` and
  `day night timer` derive, so `saves.decode` names it `clock`
  [those reads: static, the randomizer plan's RAM recipes § 2.1, not
  re-checked here].  It is the day-night clock: `0x55920` adds
  (1/30)/600 to it per update (a 600 s day), and a new game sets it to
  the next dawn, 0.25 (`0x535A0`) [verified static, re-read, the
  randomizer's R0: `thresholds/REPORT.md` § 1, § 8]; in xemu a New
  Game's first settle, in the training room, read 0.003-0.007 (Step
  R1.26's sitting; whether w1's start takes the 0.25 wasn't read).
- **`shared.sav`** is the u32 1, then one entry per shared latch key,
  {u32 name length, name, 4-byte value}, from +4.  It has no count
  field [verified xemu 2026-10-11, rz-a: in both slots read, the u32
  at +4 is the first entry's name length, and a parse from +8 finds
  no entry].  The sample's 24 is a 24-character name, not 24 records.
  The entries are the game's **global flags**: a level `latch` node
  with a name binds to the global of that name, in the map this file
  restores (the latch loader `0x6A2E0` and the `shared.sav` reader
  `0x5E980` are the only callers of its find-or-create `0x5E690`), so
  these flags carry state between levels: 29 names in the 23
  randomizer levels, such as `AirRealm_fixed`, `conveyor_on` and
  `W4_Crane` [verified static, re-read, the randomizer's R0:
  `thresholds/REPORT.md` § 1, § 11; the count verified 2026-10-12 from
  the generated level data].
- **Level saves:** § 4d.

Sources for the sitting: xemu sitting rz-a's report, § 0 (I-0), and the
randomizer plan's RAM recipes, § 6 (private evidence, outside git).  Until its Step 2.20h Modkit called the u32 at +4
`record_count`, and its `save inspect` printed it as every binary
save's record count (1057679148 "records" for `inv.sav`).

Python API: a binary save has no class of its own.  `saves.decode`
gives its `version`, `body` (the length after +8) and the u32 at +4
named by its file: `clock` for `inv.sav` (read as an f32; `None` when
not finite), `records` for a level save, nothing for `shared.sav`.
`azurkit save inspect` prints each file's kind and size (and a text
save's lines), not these fields.  Per-file decoders (e.g. one that
walks `inv.sav`'s slots) are future work.

### 4c. `signature.sav` — HMAC-SHA1 integrity digest

Exactly 20 bytes — an HMAC-SHA1 digest, keyed with the kernel's
16-byte `XboxSignatureKey`, that Azurik uses to validate every
OTHER `.sav` file in the save slot.

**Consequence for save editing**: modifying any of the other
`.sav` files without recomputing `signature.sav` will make
Azurik reject the save on load.  The hash domain is traced
(§ 7): each `.sav` name plus a NUL and its bytes, then each
subfolder's name plus a NUL, recursively, in byte order, with
`flags=0` (no per-console layer).  The key derives from the
console's BIOS: `azurkit save edit FOLDER --flash <flash image>
--mcpx <boot ROM> --iso <image> --out <dir>` re-signs an edited slot
(§ 7).  (Until 2026-10-11 this section
called it a plain SHA-1 with an unknown hash domain; § 7's April
2026 trace superseded that [verified 2026-10-11: read of
`src/azurkit/tools/saves/sign.py`, which uses
`hmac.new(key, digestmod=hashlib.sha1)`].)

Python API: `saves.decode` gives the file's 20 bytes as its
`digest` (hex); `saves.signature(slot, key)` (`sign.py`) recomputes
it, `saves.resign(slot, key)` puts it in the slot and
`saves.signed(slot, key)` checks it (§ 5, § 7).

### 4d. Level saves (`levels/<element>/<level>.sav`)

A u32 `version`, then a u32 P, the count of the level's persistent
nodes, then P records (§ 4b's table).  Empirical taxonomy:

- `version=0` + P=0 + all-zero body → level never
  visited.  About 20 of the 24 level saves in the sampled slot.
- `version=2` + P > 0 + structured body → visited.  P is the
  level's persistent-node count: 153 for w1 and 201 for d2 [verified
  ISO: the randomizer plan's `persist.py`; verified xemu 2026-10-11,
  rz-a: w1.sav's P is 153].
- **Which nodes.**  The P nodes are the level's save list, in its
  order: the `node` section's header +0x0C/+0x10
  ([`XBR_FORMAT.md`](XBR_FORMAT.md) § "Level node graph").  It holds
  every key, fragment and power generator, every lock trigger and
  `LockToggle`, the keylords, the gondola toggles and the ice-block
  melt toggles.  It holds no `latch` (latches persist by name in
  `shared.sav`, § 4b), none of the 36 `OpenNCloseToggle` switches
  (fire walls, flame spouts and three field groups), and 21 pickup
  generators are left out:
  18 consumable ones (12 `all_fuel`, town's two infinite dispensers,
  training_room's 4 large fuels) and 3 of d2's gem generators [verified
  ISO, the randomizer's R0: `wiring/REPORT.md` § 9.1].
- **Records** (the layout, Step R1.1).  For each saved node, in list
  order: {u32 n, n × f32}, the node's whole attribute array, n its
  type's attribute count; and right after it, **for a
  `critterGenerator`, its spawn state** {u32 points, points × u32
  (spawns per point), u32 cursor} [verified static, lane: the loader
  `0x65E50` calls each node's vtable slot 4 after its block, and the
  generator's slots 3 and 4 (`0x6F920`, `0x6F390`) write and read
  that state; the randomizer's R0, `wiring/REPORT.md` § 1, § 9.1].
  That accounts for the whole body: w1's 153 saved nodes give 9,308 B
  and d2's 201 give 12,248 B, the bodies measured above [verified
  2026-10-12: summed from the save lists with
  `src/azurkit/core/xbr/nodes.py`, Step R1.1's docs script].  The restore
  runs before each type's loader, so a generator keeps its restored
  point state, and a used lock's restored `key` skips the requirement
  its loader would register [static, the same report].
- **The "tail" a plain {n, n words} walk finds** (AZ-277).  Read as
  {n, n words} only, the 153 "records" of w1.sav (9,316 B) end at byte
  4,476 and 4,840 B follow, and the owner's a1.sav breaks the pattern
  at record 69 of 178 [verified xemu 2026-10-11, rz-a].  Such a walk
  drifts from the first generator's state on, and w1's first saved
  node is a `critterGenerator` [verified ISO].  Read with each
  generator's state after its block, the records end exactly at the
  end of the body, so there is no tail [inferred: the sittings' save
  files were not kept, so no real save has been parsed this way yet].

Sources for the sittings: xemu sittings rz-a's report, § 0, and rz-b1's,
§ 2.2 (private evidence, outside git).

Naming convention matches the engine's `levels/<element>/<N>`
path format seen in Ghidra string constants.

### 4e. Where the game saves and continues (engine, 2026-10-10)

Names, VAs and counts only.  Sources: the randomizer plan's engine
facts (§1 and §7) and level census (private evidence, outside git),
re-checked where marked.

- **Save points** are `gameSaveControl` nodes in the level XBRs
  ([`XBR_FORMAT.md`](XBR_FORMAT.md) § "Level node graph"): 43 in 22
  levels, each with its save id string; attributes `doSave active
  restored clearRestored` [verified 2026-10-10: counts-only re-read of
  the vanilla ISO].  The airship, its transition levels and the
  cutscene levels have none [census].
- **Continue.** The start/continue setup `0x52F50` (`game_start_setup`
  in Ghidra and the snapshot since D94 was applied on 2026-10-11;
  `dev_menu_flag_check` in the registry until AzurKit 4.2/4.3, D68) reads
  `inv.sav` (`0x58BD0`), `shared.sav` (`0x5E980`) and `loc.sav`, then
  loads the saved level [engine facts, from a decompile; not re-checked].
  The element levels a load ends with are the save's: on a load of a
  slot the only writes to the four levels are the inventory reset
  `0x57B70` (zeros) and `inv.sav`'s read (called at `0x530A6`, fread's
  copy at `0xEB925`), with LT held or not, so no level in RAM carries
  over a quit and reload; a save platform touched after a kit poke saves
  the poked levels (`0x71083`, the save `0x52A50`, the writer `0x58B50`
  called at `0x52AE7`) [verified xemu, Step X.92b, AZ-824: a write watch
  on the fork, call hooks on v0.16.4].
  On both the new-game and the continue path it then sets current HP
  to `initial hp` (`0x532A7`) and the four element-fuel values to
  `initial fuel` (`0x532BD`–`0x53360`) [verified static 2026-10-10,
  capstone; `RE_MOVEMENT.md` § "Player HP comes from settings_foo"].
  Those writes leave the caps alone.  On a new game the caps stay as
  the inventory reset `0x57B70` set them: the four fuel caps from
  `initial fuel cap` and max HP from `initial hp` (`0x52F50` calls it
  at `0x52FD0` and `0x530C7`; `0x57BCE` stores the `initial fuel cap`
  string's VA) [verified 2026-10-10: `python -m devkit re xbe calls --to
  0x57B70`, `xbe insns --operand 0x1a19c0`; max HP: `RE_MOVEMENT.md`].
  On a continue they are what `inv.sav` holds [engine facts; not
  re-checked].
- **Where the files live** [static, Step R1.26's research
  (`docs/RE_DATA.md` § "Live pickups")]: the game in progress is under
  `z:\scratch` (a level exit writes `z:\scratch\levels\...\<level>.sav`, a
  load reads it first, a death deletes `z:\scratch\levels`); a save copies
  the scratch levels into its slot, `u:\<12-character id>\` (U: is the
  title's `E:\UDATA\4d530007`). The save device holds the slot's path at
  +0x20A, empty on a new game until its first save.
- **Autosave.** `scene_state_tick` (`0x55AB0`) builds an `autosave`
  request only while the cvar `auto save on level load` is set [engine
  facts; not re-checked].
- **`inv.sav`'s layout** is the in-memory inventory's, and these
  offsets count from the inventory's start: in the file each is 4
  more, after the version word.  The first 0x18 bytes hold the f32
  clock (§ 4b) at +0, 16 bytes at +4 and 4 at +0x14 (the four element
  levels and the first-pickup popup bits, per the randomizer plan's
  RAM recipes § 2.1); then come 12 slots of {tag, value, cap} at
  +0x18 (file 0x1C: four element fuels, the five gem counts, `hlth`,
  `spow`, `mpow`), 20 fragment slots at +0xA8 (file 0xAC) and 5 key
  slots at +0x198 (file 0x19C), 12 bytes each, up to +0x1D4: 468
  bytes, 472 in the file with the version [verified 2026-10-12:
  `python -m devkit re xbe fn 0x58BD0` (the reader) and `xbe fn 0x58B50` (the
  writer) move the version, then 4, 16, 4, 144, 240 and 60 bytes at
  inventory +0, +4, +0x14, +0x18, +0xA8 and +0x198; `xbe fn 0x57B70`
  (the new-game reset) cites the 12 slot tags' strings in that order
  (`xbe strings`); verified xemu 2026-10-11, rz-a, § 4b: the file's
  bytes 4–472 equal the inventory in RAM].  The slot writer
  `0x58020` and `hlth` as slot 9 are verified (`RE_MOVEMENT.md`);
  that the 5 slots at +0x198 hold keys is the RAM recipes' (static)
  and rz-a's, which put keys in slots 0–2 and read them back from
  the file.

## 5. Python API

```python
from azurkit.tools import saves

slot = saves.Slot.read("exported_save/")      # a slot's folder; saves.slots(hdd) reads an xemu HDD image's slots
for file in saves.decode(slot):               # what each file holds, by path: its kind, size and a text save's lines
    print(file["path"], file["kind"], file["size"])

# Text saves: a line's index counts after the fileversion= line; line 4 is the armor gauge (§ 4a).
slot, changed = saves.edit(slot, [{"file": "magic.sav", "line": 4, "value": "99.000000"}])

key = saves.key(flash, mcpx, xbe)             # the console's signature key, in memory only (§ 7)
saves.resign(slot, key).write("patched/")     # a new folder; slot.zip() gives the slot as a zip
```

`saves.edit` makes every edit or none and names each it can't make
(a file the slot hasn't, no text save, a line past its end).

## 6. CLI

```
azurkit save inspect exported_save/        # a slot's folder
azurkit save inspect xbox_hdd.qcow2        # every Azurik slot on an xemu HDD image, read-only
```

`inspect` prints each slot's id with its file and folder counts, then
each file's path, kind and size, and a text save's lines by index (the
`fileversion=` line not counted). A real `SaveMeta.xbx` can hold
only a `Name` line and no `TitleName` (the one we inspected did).

## 7. Signature algorithm

**Algorithm traced (April 2026).**  Ghidra decomp of
``FUN_0005c4b0`` + its surrounding caller at VA ``0x0005c920``
(this section's VAs are the USA release's; Europe's walker, sign and
verify are the same code 0x50 lower [verified 2026-10-12, the region
study]) shows the sign / verify path uses Xbox's stock
``XCalculateSignatureBegin / ...Update / ...End`` trio with
``flags=0`` (no per-console HDKey outer layer), which reduces
to **HMAC-SHA1(XboxSignatureKey, tree_bytes)**.

### Tree-walk order (from the decomp)

```
hmac = HMAC-SHA1.Init(XboxSignatureKey)

def walk(dir):
    files = [f for f in sorted(dir) if f.name.lower() != "signature.sav"
                                   and  f.name.lower().endswith(".sav")]
    subdirs = [d for d in sorted(dir) if d.is_dir()
                                     and d.name not in (".", "..")]

    for f in files:            # byte order: the game sorts with case-sensitive strcmp
        hmac.update(f.name.encode("ascii") + b"\0")
        with open(f, "rb") as fh:
            while chunk := fh.read(0x4000):
                hmac.update(chunk)

    for sd in subdirs:         # byte order, like the files
        hmac.update(sd.name.encode("ascii") + b"\0")
        walk(sd)

signature_bytes = hmac.digest()      # 20 bytes
Path("signature.sav").write_bytes(signature_bytes)
```

The entry point at ``0x0005c920`` confirms ``flags=0`` via the
``PUSH 0x0`` two instructions before ``CALL XCalculateSignatureBegin``
(see `devkit/re/data/ghidra_snapshot.json` → ``calculate_save_signature``).

### The key: derived from the console's BIOS

[verified xemu 2026-10-13, Step 2.37 (AZ-338): its sittings keyprobe and savecheck, below]

- **The game reads the kernel's `XboxSignatureKey`.**
  `XCalculateSignatureBegin` (USA 0xE2BC9) keeps the pointer in its
  thunk slot (USA 0x18F4D4, Europe 0x191654; kernel export 325) and
  starts a plain HMAC-SHA1 with it (0xE2AB5, the 0x36 pad; End's outer
  pass 0xE2B1C, the 0x5C pad).
- **The kernel derives it when it launches the XBE:**
  `XboxSignatureKey = HMAC-SHA1(certificate key, XBE cert+0xC0)[:16]`.
  The certificate signature keys of the USA and Europe XBEs are
  byte-equal, so both releases share the key.
- **The certificate key is a kernel constant** (the same in every retail
  kernel [inferred: the XDK's scheme; only Complex 4627 was read]). In
  Complex 4627 it is in the kernel's `STICKY` section (VA 0x8003AFF8). In
  the flash image it is in the second-stage loader (2BL), the 0x6000
  bytes below the image's top 0x200, at +0x7C; the MCPX 1.0 boot ROM's
  16 bytes at +0x1A5 RC4-decrypt the 2BL. Both of the owner's Complex
  4627 images hold it there.
- **Seen in xemu.**
  - Sitting keyprobe: a cold-booted vanilla USA game, halted at its entry
    0xE3039, has 0x8003B118 in its thunk slot. The 16 bytes there sign the
    owner's SaveGame #1 (D98's HDD): the HMAC of § 7's walk equals its
    `signature.sav`. In a 128 MiB RAM dump, one window (physical 0x3AFF8)
    gives that key as its HMAC over cert+0xC0, and its sha256[:12] is the
    2BL key's.
  - Sitting savecheck: that slot's `loc.sav` line 0 edited from
    `levels/water/w1` to `levels/water/w2` by `save edit`, on a clone of
    D98's HDD, cold-booted on vanilla USA with no packs. Re-signed with
    `--kernel Complex_4627.bin --mcpx mcpx_1.0.bin`: verify (0x5C990)
    returned AL = 1, the game loaded `levels/water/w2` and the player tick
    ran. The same edit unsigned: AL = 0 and "Unable to load saved game."
- **Why the April 2026 recovery found nothing** (three slots, the
  EEPROM, the XBE and two RAM dumps; until Step 2.37 this section listed
  its scans): its candidates never include the kernel's certificate key.
  Its RAM scans for the derived key also missed it [cause not found]. Its
  "pointer that changes between boots" was RAM at physical 0x18F4D4, not
  the XBE's VA 0x18F4D4 [inferred].

### Re-signing an edited save

```
azurkit save edit exported/ --set loc.sav:0=levels/water/w2 \
    --flash Complex_4627.bin --mcpx mcpx_1.0.bin --iso <your image> --out patched/
```

`--flash` takes the flash BIOS image, with `--mcpx`, its MCPX 1.0 boot
ROM (xemu's usual pair; Modkit called it `--kernel`). It also takes any
file holding the certificate key as is: a 16-byte key file,
Cxbx-Reloaded's `keys.bin`, a RAM dump. `save edit` reads the game's
certificate from `--iso`'s XBE, derives the key in memory
(`src/azurkit/tools/saves/sign.py`) and writes the slot to `--out`, a
new folder, with its new `signature.sav`, with or without an edit: with
no `--set` it re-signs the slot as it is, a save edited elsewhere
included (Step 2.84). An HDD image's slot is named with `--slot`. The
repo never holds a key, only the certificate key's fingerprint
(sha256[:12] `0961021c45b7`, `sign.CERT_KEY_SHA256_12`). A flash image
for a later boot ROM is not read [untested]. `--xbox-signature-key` and
`save key-recover` are retired (D181); `--flash` is the one way to
re-sign.

Until Step 2.37 no key was known, and the `qol_skip_save_signature` pack
patched verify (USA 0x5C990, Europe 0x5C940) to `MOV AL, 1 ; RET` so an
edited save loaded. The pack is retired; its name fails by name.

### Python helper

The walk is `azurkit.tools.saves.sign.signature`; the key derivation
is `cert_key`, `title_key` and `signature_key` beside it, which
`azurkit.tools.saves.key` joins.

### Remaining unknowns / backlog

- **An `inv.sav` decoder.**  The file is the inventory as it is in
  RAM (§ 4b, § 4e), and the u32 at +4 is its first field, an f32
  clock, not a count (AZ-275).  What's left is a decoder that
  exposes the slots.
- **Level-save records and tail.**  A visited w1.sav holds its 153
  records and then a tail (§ 4d); the records are not all
  {n, n words}, and the tail is not decoded.  Settle which records
  carry more than their n words, then the tail: diff two saves that
  differ by one known change.
- **`SaveImage.xbx` decoder.**  Opaque bytes today; Xbox ARGB
  swizzle decode would let users preview thumbnails in a future
  save editor.

## 8. Relationship to other docs

- Code: [`src/azurkit/tools/saves/`](../src/azurkit/tools/saves/)
- Tests: [`tests/test_saves.py`](../tests/test_saves.py),
  on synthetic saves built in-test. The repo tracks no save (D59):
  the leak guard ([`tests/_leak_guard.py`](../tests/_leak_guard.py))
  refuses a `.sav` or `.xbx` file and a text-save or `SaveMeta.xbx`
  header under any name.
