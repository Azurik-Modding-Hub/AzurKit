# Azurik XBR file format

Byte-level reference for the `.xbr` container that Azurik uses for
every bundled data file, and (§ "Packs and mods files that edit `.xbr`
files") how AzurKit edits one.  Ported from Azurik_Modkit's `docs/`
(`XBR_FORMAT.md`, with `XBR_PACKS.md` merged in): a `tests/test_*.py`
or a module named in a [verified] note that AzurKit lacks names
Modkit's tree, where the finding was made; AzurKit's parsers are:

- [`src/azurkit/core/xbr/`](../src/azurkit/core/xbr/) — the structural
  document model used by the mod infrastructure.
- [`src/azurkit/core/xbr/nodes.py`](../src/azurkit/core/xbr/nodes.py) —
  the one TOC reader (every tool and the document model use it,
  AZ-124) and the string scan behind `xbr diff` / `audio dump`.
- [`src/azurkit/tools/characters/index_xbr.py`](../src/azurkit/tools/characters/index_xbr.py)
  — index.xbr's records (AZ-218) and their sorted insert (Step 2.86).
- [`src/azurkit/core/xbr/append.py`](../src/azurkit/core/xbr/append.py) — new
  named resources appended to an archive (§ "Appending resources",
  Step 2.86).
- [`src/azurkit/core/xbr/keyed.py`](../src/azurkit/core/xbr/keyed.py)
  — config.xbr keyed-table semantics.

Everything below is pinned by
[`tests/test_xbr.py`](../tests/test_xbr.py)`::test_every_vanilla_xbr_round_trips_to_its_manifest_hash`
(every vanilla XBR of both releases parses and writes back to the hash
its release's manifest, `src/azurkit/core/manifests/`, records): if the
format changes under us (e.g. a different ISO revision), it fails
loudly. It reads the player's images (`AZURKIT_ISO`,
`AZURKIT_ISO_EUROPE`, else the user data folder's).

---

## File anatomy

```
+-------------------------------+  0x00
| Header (0x3C bytes)           |
+-------------------------------+  0x3C
| TOC entry 0   (16 bytes)      |
| TOC entry 1                   |
| ...                           |
| TOC entry N-1                 |
| (16 zero bytes in vanilla)    |
+-------------------------------+
| (pad to the next 0x1000 —     |
|  preserved verbatim)          |
+-------------------------------+  header[0x10] = data_start
| Section payload 0             |
| Section payload 1             |
| ...                           |
+-------------------------------+
| (pad to the next 0x1000)      |
+-------------------------------+  header[0x18]
| Trailer: per-tag rows,        |
|  relocations, named rows,     |
|  name pool                    |
+-------------------------------+  EOF
```

Each TOC entry points at a **payload region** elsewhere in the file
via its stored offset, which is **relative to the data-area start**
(the u32 at header +0x10) — not absolute.  Payloads follow in TOC
order and never overlap; vanilla files leave gaps between them,
often aligned to 0x1000.  The document model preserves every byte,
including gaps, to guarantee byte-identity round-trip.

After the last payload comes the trailer the header indexes
(§ "The trailer"); it ends at EOF.

Exception: `loc.xbr` is a 60-byte stub — correct `xobx` magic, a
bare 0x3C-byte header with `toc_count` 0, so its TOC is empty.

---

## Header (0x00 — 0x3B)

| Offset | Size | Field        | Status     | Notes |
|--------|------|--------------|------------|-------|
| 0x00   | 4    | `magic`      | **known**  | Always `b"xobx"`. |
| 0x04   | 4    | `version`    | **known**  | `4` in every vanilla XBR.  The engine's header check `0xBDBB0` returns the header only when the magic is `xobx`, the u16 at +0x04 is 4 and the u16 at +0x06 is 0; it is called only from `0xA5735` and `0xA57D0` [verified 2026-10-10: capstone, and `python -m devkit re xbe calls --to 0xBDBB0 --iso iso/usa.iso`; first found in the AZ-124 evidence, 2026-10-09]. |
| 0x08   | 4    | u32          | UNKNOWN    | Zero in every vanilla XBR. |
| 0x0C   | 4    | `toc_count`  | **known**  | Number of TOC entries. |
| 0x10   | 4    | `data_start` | **known**  | File offset where section payloads begin — in vanilla `align_up(0x40 + (toc_count + 1) * 16, 0x1000)`.  Every TOC offset is relative to this.  Verified on all 41 full-header vanilla XBRs. |
| 0x14   | 4    | `tag_rows`   | **known**  | Count of the trailer's per-tag rows (8 bytes each). |
| 0x18   | 4    | `trailer`    | **known**  | File offset of the trailer: a multiple of 0x1000, at or after the last payload's end. |
| 0x1C   | 4    | `reloc_count`| **known**  | Count of relocation entries (4 bytes each). |
| 0x20   | 4    | `reloc_off`  | **known**  | File offset of the relocation table. |
| 0x24   | 4    | u32          | **known**  | Count of 12-byte records; 0 in every vanilla XBR. |
| 0x28   | 4    | u32          | **known**  | File offset of those records. |
| 0x2C   | 4    | `named_count`| **known**  | Count of named-resource rows (8 bytes each). |
| 0x30   | 4    | `named_off`  | **known**  | File offset of the named-resource table. |
| 0x34   | 4    | `pool_off`   | **known**  | File offset of the name pool. |
| 0x38   | 4    | `pool_size`  | **known**  | Size of the name pool, which ends at EOF. |

All header offsets are file-absolute.  0x14–0x38 index the trailer
(§ "The trailer") [verified 2026-10-11, 41/41 full-header vanilla XBRs:
`[0x18] + 8·[0x14] = [0x20]`, `[0x20] + 4·[0x1C] = [0x28]`,
`[0x28] + 12·[0x24] = [0x30]`, `[0x30] + 8·[0x2C] = [0x34]`,
`[0x34] + [0x38]` = the file size, `[0x18] % 0x1000 = 0`, every
payload ends at or before `[0x18]`; and `[0x04] = 4`, `[0x08] = 0`, TOC
entry 0's offset 0; the hub mining's HM-01, re-run by Step 2.16l's
check script (private evidence, counts only)].

**Implementation note.** The document model round-trips the header
and the TOC verbatim.  Only
[`append.py`](../src/azurkit/core/xbr/append.py) rewrites them (§ "Appending
resources"): it moves the trailer and patches 0x18, 0x20, 0x28, 0x30
and 0x34 (and 0x0C, 0x10, 0x2C, 0x38 for what it adds).

**The engine's accessors.** Three small functions after the header
check take the header (in EAX; 0xBDC30 in ECX) [verified 2026-10-11:
capstone]: `0xBDBF0`
returns `[+0x18]` (the trailer's offset), `0xBDC30` returns the header
pointer plus `[+0x18]` (the trailer's address), and `0xBDC10` returns
`8·[+0x14] + 4·[+0x1C] + 12·[+0x24] + 8·[+0x2C] + [+0x38]`, the
trailer's size.  None has a direct caller (`python -m devkit re xbe calls --to
0xBDBF0`, the same for `0xBDC30` and `0xBDC10`,
2026-10-10).

---

## Table of contents (from 0x3C)

`toc_count` entries of 16 bytes, little-endian; entry k is at
`0x3C + 16k`:

| Offset | Size | Field         | Notes |
|--------|------|---------------|-------|
| +0     | 4    | `offset`      | Payload offset **relative to the data-area start** (header +0x10): `TocEntry.rel_offset`.  The absolute offset `header[0x10] + offset` is `TocEntry.file_offset`. |
| +4     | 4    | `size`        | Payload length in bytes. |
| +8     | 4    | `tag`         | 4-char ASCII (e.g. `"tabl"`, `"node"`, `"surf"`, `"indx"`). |
| +12    | 4    | `flags`       | The payload's alignment: 8, 16 or 128.  Round-tripped as-is. |

The header's `toc_count` ends the TOC.  Vanilla files follow the last
entry with 16 zero bytes, which nothing needs.

[verified 2026-10-09, AZ-124] This is the engine's layout.  At
0xA5619 (in 0xA55F0) it addresses entry k as `header + 0x3C + 16k`
and reads +0 as the offset and +4 as the size; the loop at 0xA5840
strides 0x10, passes entry+8 (the fourcc) to 0xA9200 and computes
the payload as `[entry+0] + header[0x10] - [entries[0]+0]` (entry 0's
offset is 0 in vanilla).  Read this way, the payloads of all 41
full-header vanilla XBRs start at `header[0x10]` and tile the file in
TOC order (pinned by `tests/test_xbr_toc_scan.py`).  Until AZ-124
every reader took 16-byte rows from 0x40 as `(size, tag, flags,
offset)`, which pairs each entry's size with the next entry's offset
(the last with 0), and used that offset as absolute; payloads
overlapped in 40 of the 41 files, and config.xbr's labels came out
shifted by one table (AZ-113).
[`toc_scan.parse_toc`](../src/azurkit/core/xbr/nodes.py) is now the one
reader, and every slice starts at the entry's `file_offset`.
`config.keyed_tables` still adds 0x1000 (config.xbr's data area) to
its `KEYED_SECTION_OFFSETS` labels.

**`flags` is the alignment** [verified 2026-10-11: all 78,810 TOC
entries of the ISO have `offset % flags == 0`; that the engine uses it
so is inferred, with no Ghidra check; HM-06].  It isn't constant per
tag: `surf` is 128 ×10,296 and 8 ×212, `sprv` 128 ×320 and 8 ×103; the
other tags take one value (16 for `bmsh`, `body`, `rdms`, `sdsr`; 8 for
the rest).  A writer that moves a payload must keep its alignment.

Two accessors beside the header check compute the same layout:
`0xBDBE0` returns header + 0x3C (entry 0) and `0xBDC00` returns
0x3C + 16 × `toc_count` (the TOC's end) [verified 2026-10-10:
capstone].  Neither has a direct caller (`python -m devkit re xbe calls --to
0xBDBE0`, and `--to 0xBDC00`, find 0) and no
`.rdata`/`.data` dword points at either, so the engine inlines the
arithmetic where it needs it (as at 0xA5619) and these are unused
[inferred].

### Tag inventory

18 distinct tags, populated by counting TOC entries across all 42
vanilla XBRs.  AzurKit's `Document` (`core/xbr/document.py`) keeps
every payload's bytes as they are and parses only config.xbr's keyed
tables (`tabl`) into fields: every tag round-trips, and only a keyed
cell has an edit.

| Tag     | Rows | Appears in                       | Parser state |
|---------|------|----------------------------------|--------------|
| `tabl`  | 18     | config.xbr only                | **keyed-table** or **variant-record** depending on its stored offset.  See below.  Only `tabl` entries get these overlays (AZ-124). |
| `indx`  | 1      | index.xbr only                 | **index-records** (round-trip only — see below); [`index_xbr.py`](../src/azurkit/tools/characters/index_xbr.py) decodes its records (AZ-218). |
| `rdms`  | 28547  | 35 files                       | RawSection.  Most common tag in the game data. |
| `pbrc`  | 22721  | 35 files                       | RawSection. |
| `surf`  | 10508  | 39 files                       | RawSection.  Textures: 10,296 images and 212 animated frame lists (§ "Graphics resources").  Stride classifier in [`xbr_inspect.py`](../devkit/xbr/inspect.py). |
| `tern`  | 5976   | 34 files                       | RawSection; collision meshes (§ "`tern` (collision)"). |
| `pbrw`  | 5826   | 35 files                       | RawSection. |
| `wave`  | 2266   | 36 files (fx.xbr alone has 700)| RawSection.  Audio codec partially reversed in [`audio_dump.py`](../devkit/audio/dump.py) / `docs/RE_DATA.md`. |
| `banm`  | 712    | characters.xbr / diskreplchars.xbr | RawSection.  Animation bundles. |
| `sdsr`  | 426    | 35 files                       | RawSection.  Streamed audio: each is the sample data behind one `wave`, referenced exactly once, from that wave's +16 (426/426; english.xbr's 134 hold 23.15 MB); not collision (HM-12). |
| `gshd`  | 423    | 36 files                       | RawSection. |
| `sprv`  | 423    | 36 files                       | RawSection. |
| `ndbg`  | 263    | 35 files                       | RawSection.  One per `node`: names its records (§ "Level node graph"). |
| `node`  | 263    | 35 files                       | RawSection.  In level XBRs, the level's node graph; its record table and common record fields are decoded (§ "Level node graph"), but no repo code parses them. |
| `bmsh`  | 240    | characters.xbr / diskreplchars.xbr | RawSection. |
| `body`  | 160    | characters.xbr / diskreplchars.xbr | RawSection. |
| `levl`  | 33     | 33 level XBRs (1 each)         | RawSection.  The level's sky anchor, cells and static geometry (§ "`levl`"). |
| `font`  | 4      | interface.xbr only             | RawSection. |

"RawSection" (Modkit's name, kept in the table) = the payload's
bytes are kept as they are and the document model decodes no
structure; other modules read some of them (§ each tag's section).

---

## The trailer (after the last payload)

Every full-header XBR ends with a trailer that header words 0x14–0x38
index (§ "Header"): four tables back to back from `header[0x18]`, then
the name pool, which ends at EOF.  Found by the hub mining from Azurik
Level Studio's reader (Modkit's hub mining, HM-01, HM-02, HM-04;
MIT, knowledge only) and re-checked on the vanilla ISO by Step 2.16l
[verified 2026-10-11: Step 2.16l's check scripts, counts only].  Nothing in the
document model round-trips it as file bytes; only `append.py` moves
it and adds named rows and names (§ "Appending resources").

### Per-tag rows (`header[0x14]` × 8 bytes at `header[0x18]`)

One `(fourcc, u32)` row per distinct tag of the file (the set equals
the TOC's in 41/41).  The u32 is the same for a tag in every file, so
it is probably the tag's format version [inferred]:

| Tag | Value | Tag | Value | Tag | Value |
|---|---|---|---|---|---|
| `banm` | 6 | `levl` | 34 | `sdsr` | 0 |
| `bmsh` | 2 | `ndbg` | 3 | `sprv` | 5 |
| `body` | 16 | `node` | 93 | `surf` | 4 |
| `font` | 1 | `pbrc` | 2 | `tabl` | 1 |
| `gshd` | 9 | `pbrw` | 2 | `tern` | 4 |
| `indx` | 3 | `rdms` | 15 | `wave` | 4 |

A writer that adds a tag to a file must add its row.

### Relocations (`header[0x1C]` × 4 bytes at `header[0x20]`)

Each entry is the offset, from the data area (`header[0x10]`), of a
u32 field that holds a TOC index: a cross-resource reference.  When a
run loads, the run loader 0xA55F0 binary-searches the rows for the
run's span and adds the archive's slot base (`[state+0x20]` less
`header[8]`) to every field in it (0xA5633-0xA569D), so the index
becomes a handle, not a pointer [static, Step 2.157's read].  A field
the table doesn't list stays a bare index, read as a handle of slot 0.
Everything else inside a payload is self-relative: all 34,693 decoded
references of the 226 fx graphs land inside their own payload [data,
Step 2.157].  So a copy of a resource is its bytes plus its rows at the
same inner offsets, each naming its target's copy or the target
([`clone.py`](../src/azurkit/core/xbr/clone.py), Step 2.157).
122,074 entries on the disc, all 4-aligned, every target below its
file's TOC count, ascending in 41/41 files; `config.xbr` and
`index.xbr` have none.  All 23 groups (source tag → target tag; they
sum to the 122,074) [verified 2026-10-11]:

| Edge | Count | Edge | Count |
|---|---|---|---|
| `rdms` → `gshd` (its +4) | 28,547 | `node` → `surf` | 1,475 |
| `levl` → `rdms` | 16,846 | `bmsh` → `gshd` | 694 |
| `levl` → `pbrc` | 12,617 | `wave` +16 → `sdsr` | 426 |
| `node` → `rdms` | 11,701 | `node` → `gshd` | 279 |
| `node` → `pbrc` | 10,104 | `node` payload +0x1C → `ndbg` | 263 |
| `gshd` → `sprv` | 8,655 | `body` → `bmsh` | 240 |
| `gshd` → `surf` | 8,632 | `levl` → `node` | 33 |
| `node` → `tern` | 5,947 | `levl` → `gshd` | 33 |
| `surf` → `surf` (frame lists) | 4,950 | `levl` → `tern` | 29 |
| `node` → `wave` | 4,751 | `levl` → `surf` | 22 |
| `levl` → `pbrw` | 4,229 | `font` → `surf` | 4 |
| `node` → `pbrw` | 1,597 | | |

So inserting or deleting a TOC entry renumbers exactly these fields
and the named rows below; `index.xbr` holds no TOC index.  89 `gshd`
and 3 `surf` (34 of those `gshd` in fx.xbr) are neither relocated nor
named: candidate dead data [inferred].

### 12-byte records (`header[0x24]` at `header[0x28]`)

The count is 0 in every vanilla XBR.

### Named resources (`header[0x2C]` × 8 bytes at `header[0x30]`)

Each row is `u32 TOC index, u32 offset` into the name pool at
`header[0x34]` (`header[0x38]` bytes of NUL-terminated names).  An
XBR names its own resources here; only some resources have a row.
[`toc_scan.named_resources`](../src/azurkit/core/xbr/nodes.py) reads it
(AZ-217), and `audio dump` names waves from it.

| Archive | Named rows |
|---|---|
| config.xbr | `config/<table>` ×18, in TOC order (`KEYED_SECTION_OFFSETS` agrees 18/18) |
| fx.xbr | 574 `wave`, 346 `surf`, 113 `node` (the other 126 waves are only relocated: none is both) |
| characters.xbr | 710 `banm`, 158 `body`, 113 `node` |
| interface.xbr | 618 `surf`, 8 `wave`, 4 `font` |
| english.xbr | 234 `wave`, 125 `surf` |
| a level | its `levels/…` key (1–3 rows) |
| index.xbr | `index` |

3,073 rows on the disc, no duplicate (tag, name) in a file.
`index.xbr`'s 3,072 records repeat all of them but index.xbr's own
(§ "`indx` payload").

### Trailing bytes

The engine loads a file longer than its pool's end: the xemu oracle
grew `training_room.xbr` by 64 KiB of zeros and it loaded and played
once `filelist.txt` was rewritten [verified in xemu 2026-10-09, the
oracle's sitting that day].  Level Studio
refuses such a file.

### Region

The trailer layout, the named tables, the node records and the counts
Level Studio's tests pin on its EU disc all hold on our USA disc
(HM-29: its 30 w1 fixture nodes match ours in every field), so the
shared data XBRs look region-independent [inferred: byte identity per
file is unproven without the EU hashes].

---

## Load runs and the 40 MiB budget

The game never loads one TOC entry alone (Step 2.158, read statically on
USA's XBE and measured in xemu; [`RE_XBE.md`](RE_XBE.md) § "The load runs
and the 40 MiB budget"):

- **A run** is a TOC entry whose offset is page-aligned (0x1000) and the
  entries after it, in TOC index order, that start in its page. The run
  builder 0xA4C00 walks the TOC by index, not by file offset: from the
  entry asked for it goes back to the nearest page-aligned row
  (0xA4C30-0xA4C3D), then forward while a row's `offset & ~0xFFF` is the
  head's offset (0xA4C60-0xA4C71), and reads the head's offset to the
  last member's end as one block (0xA4CF4). An entry past its head's page
  with no page-aligned entry before it is in no run, and can't load. In
  vanilla, index order is offset order and every entry is in a run:
  characters.xbr's 3,394 entries in 2,655 runs, fx.xbr's 3,572 in 2,091.
  [`toc_scan.runs`](../src/azurkit/core/xbr/nodes.py) is that partition;
  `model inspect` and the payload rewrite read it.
- **One budget** holds every loaded run of every archive (level,
  characters, fx, interface, config): the run allocator 0xA4890 rounds a
  run up to whole pages and refuses it when `[0x1BF400]` (used) plus its
  size passes `[0x1BF404]` (the limit), 0x2800000 = 40 MiB, set once at
  boot (USA 0x596C6; Europe 0x59706, `[0x1C13A4]`; `qol_memory_budget`
  raises it, to 42 MiB in every build by default, Steps 2.162b and 2.162d). Both contiguous
  (write-combined) and virtual runs count. The memory check 0x58D00
  lowers it only when the kernel's free physical memory drops under 1 MiB
  (at 40 MiB it never did in xemu, on a 64 or a 128 MiB machine; raised,
  the lowest it left was 42.38 MiB: 44 held through a1's inventory and fell
  at the e2 and w1 changes, 48-52 were cut already at a1).
- **A refused run** makes 0xA64D0 evict runs no one references and that
  weren't used this frame, and retry; with nothing left to evict the run
  loads as 0 and `[0x1BF5A0]` is set. A body whose `bmsh` run is 0 isn't
  drawn (0x3F16D skips the LOD); a missing `gshd` skips its group.
- **What fails first is the level** (on a load; in play at a1's save,
  the inventory screen, below). Most of the 40 MiB is a cache of
  unreferenced runs; what a level references, from w1 by the debug warp
  (xemu): e2 18.03 MiB, e5 14.84, e6 14.77, f4 14.57, a1 12.96, town
  12.80, f3 12.63, w1 12.27, a6 12.25, w4 11.99, f1 11.83, a3 10.65, e7
  10.59, d1 10.46, f6 9.25, d2 9.21, f2 9.03, a5 8.91, w2 8.89, w3 8.67,
  life 7.96, airship 6.20. The player's body runs stay referenced in every
  level, so they add to each. As room runs out the level's textures go
  missing silently (blurred floors, a statue gone), then the next level
  change hangs on "Loading...". A level loaded from a save has less room
  than one reached by a level change: a1's save, the tightest of the nine
  D98 saves (Step 2.158's re-run), keeps full detail on a fresh load with
  15.79 MiB of a player build's own runs (the clips the build bakes onto
  the body included: female_2's holds 2.18 MiB besides her `bmsh` and
  `body`) and has lost its tree's leaf textures by about 17.7 with no run
  failing, w1's and e2's saves their save platform's grille by about
  20.9; e2 from w1 by the debug warp keeps full detail to about 21.4
  and hangs past about 23.1 (no save load hung up to 22.0). Play needs
  more: interface.xbr's runs load while the inventory screen (BACK) is
  open, and at a1's save it stays whole with 12.67 MiB and loses pieces
  with 15.79, its share of the budget stuck near 1 MiB against female_2's
  7.7 (Step 2.158b, AZ-667; w1's and e2's stay whole at 15.79, the
  other six saves' are unmeasured). `model inspect` warns past 10 MiB
  and errs past 12, and the player build
  refuses a body past 12 MiB; the 13 levels with no save are
  unmeasured. A run's own size is no limit:
  a `bmsh` run of 5.6 MB (14x vanilla's largest) loads and draws in w1,
  f6 and e2.
- **Europe** has the same 40 MiB, and every level XBR, characters.xbr and
  fx.xbr is byte-identical to USA's (only index.xbr differs), so these
  numbers hold for both releases.

## Appending resources

[`append_resources`](../src/azurkit/core/xbr/append.py) adds named resources
to an archive and
[`add_index_records`](../src/azurkit/tools/characters/index_xbr.py) their keys to
index.xbr (Step 2.86; the build-time bake of Step 2.87 adds clips to
characters.xbr with them).  A new key needs both: the index record
makes the name map's node, and the archive's named row gives it a
handle ([`RE_DATA.md`](RE_DATA.md) § "How a name resolves").

What `append_resources` writes:

- **Payloads** on a page (0x1000) each, after the last payload; the run
  builder 0xA4C00 loads runs from page-aligned TOC offsets.  Each gets
  the next TOC entry, with the largest `flags` (alignment) the
  archive's entries of its tag carry; a page satisfies every one.
- **The TOC** grows into the padding before `data_start`.  Once it
  needs more, `data_start` grows by whole pages, to vanilla's
  `align_up(0x40 + (toc_count + 1) * 16, 0x1000)`: characters.xbr's
  3,394 entries leave room for 185 (its `data_start` 0xE000).  TOC
  offsets are relative to the data area, so no old offset changes.
- **Named rows** after the last one and **names** at the pool's end
  (characters.xbr's rows aren't sorted: 0xA5570 walks them all).
- **The trailer** moves to the page after the last payload; the
  header's offsets follow it.  The per-tag rows, relocations, 12-byte
  records, old named rows and old names stay byte-identical.

It refuses (`XbrStructuralError`, D35) a name already in the archive,
one that isn't lower-case ASCII (lookups lowercase the key, 0xA5B10),
and a tag the archive doesn't hold (0xA54F0 checks every per-tag row's
version against the engine's, and a new tag would need its row).

`rewrite={toc index: payload}` replaces a payload in place, for a body
whose marker table grows: every relocated field inside it must keep its
value, the old bytes past its end become zeros, and the TOC entry's
`size` changes. Since Step 2.154 a payload may outgrow the slack before
the next one ([`rewrite_payloads`](../src/azurkit/core/xbr/append.py)): the
next payload and every one after it move by the fewest whole pages that
make room, so each keeps its alignment and its offset in its page; their
TOC offsets and every relocation entry inside them move by the same
delta, the trailer follows, and no TOC index, relocation value, named row
or name changes. Where the next payload isn't page-aligned it shares the
grown one's load run (§ "Load runs and the 40 MiB budget": vanilla
characters.xbr's 63 `gshd body` runs, 22 `surf rdms`, 19 `rdms rdms`,
...), and moved a page on it would load in no run; since Step 2.158 it
moves to the first page start after the grown payload instead, the head
of a run of its own, and the rest of its old page follows it, each at its
old distance from it where that keeps its alignment (its TOC flags: 8, 16
or 128), else at its own alignment after the one before (15 of
characters.xbr's 739 such cases, 28 of fx.xbr's 1,481); every later
payload moves by whole pages, and the result's runs are checked: every
entry in one and each re-paged entry a head. The payloads it rewrites
today (`body`, `bmsh`, `banm`, `indx`) are all followed by a page-aligned
one, so this is for a texture or material grown in place [the re-paged
run's load is not yet seen in xemu]. `rewrite_payloads(relocated={toc index: offsets})` also
gives a rewritten payload a new set of relocated fields (a mesh with more
or fewer groups), so the relocation count may change [not yet seen in
xemu: Step 2.86's sitting moved every payload a page in the file but not
against the data area].

`add_index_records` rebuilds index.xbr's one `indx` payload: the
records, old and new, sorted by key (bytewise; vanilla's are lower case
and sorted), the old strings kept and the new ones after them, through
`append_resources`' rewrite, which moves the trailer by whole pages.

Since Step 2.157 a `NewResource` carries `relocs`, the offsets of its
fields that hold a TOC index (already the final index: a new entry's is
the count plus its place among the new ones), and they become
relocation rows after the old ones, ascending (every new payload sits
after every old one); `header[0x1C]` grows by their count and the
12-byte records, named rows and pool move by 4 bytes a row.  A
`NewResource` with `name=None` gets a TOC entry and no named row: it is
reached only through a relocated field, as vanilla's `rdms`, `gshd`,
`sprv`, `pbrc`, `tern` and most `surf` are (0xA59F0 builds the run of a
handle that has none, 0xA5980/0xA4C00 [static]).  `appended(count, data)`
reads an archive's entries past `count` back as `NewResource` values
with their names and rows, so W28 adds a build's entries again with
theirs.  A `banm` holds no TOC index.  Pinned by
`tests/test_index_xbr.py::VanillaIndex::test_resources_appended_to_characters_xbr_resolve_through_index_and_named_rows`:
186 clips (`data_start` moves a page), their 186 records and a body
grown in place.  xiso.pack moves the grown file past the image's end
and rewrites both `filelist.txt` lines, so the game re-copies them to
its HDD cache.

**The engine loads such an archive** [verified in xemu 2026-10-15,
Step 2.86's sitting]: a
USA build whose characters.xbr carried 186 appended clips (3,394 → 3,580
TOC entries, `data_start` 0xE000 → 0xF000, 186 named rows, 75.0 MB) and
index.xbr 186 more records booted from `vanilla-ig-w1`'s save and
loaded w1, its `.text` the build's.  It wrote 75,238,400 B more to the
HDD than the vanilla control (the two grown files are 75,198,753 B):
the game re-copied both and played from them.  No new key was looked
up there; Step 2.87's sitting plays one.

---

## Keyed-table sections (all 18 config.xbr tables)

Section-local offsets, measured from the section's payload start
(the entry's `file_offset`, `header[0x10]` + its stored offset):

```
0x0000 .. 0x0013     Table header (20 bytes = 5 x u32)
0x0014               Row headers (8 bytes each, num_rows rows)
cell_off + 0x10      Cell grid (16 bytes each, column-major)
  .. end
(after cells)        All string data — row names AND type-2 cell
                     strings (self-relative)
```

There is **no leading string pool**.  Every one of vanilla
config.xbr's 364 row names and 9748 type-2 cell strings resolves to
an offset past the end of that section's cell grid and inside its
TOC payload.

### Table names

config.xbr names its own tables in its named-resource table (§ "The
trailer"): one `config/<name>` row per table (the names the engine
loads them by, e.g. `config/armor_properties` at 0x3C700), in the
order of the tables' payloads. `KEYED_SECTION_OFFSETS`
([`sections.py`](../src/azurkit/core/xbr/keyed.py)) is that list, keyed by
the TOC entry's stored offset (`rel_offset`), and is the one copy
(`config.keyed_tables` imports it):

| `rel_offset` | Name | `rel_offset` | Name |
|---|---|---|---|
| 0x000000 | `armor_hit_fx` | 0x05A000 | `critters_flocking` |
| 0x002000 | `armor_properties` | 0x05D000 | `critters_item_data` |
| 0x004000 | `attacks_anims` | 0x060000 | `critters_maya_stuff` |
| 0x006000 | `attacks_transitions` | 0x065000 | `critters_mutate` |
| 0x008000 | `critters_critter_data` | 0x066000 | `critters_sounds` |
| 0x01A000 | `critters_damage` | 0x077000 | `critters_special_anims` |
| 0x035000 | `critters_damage_fx` | 0x07A000 | `critters_walking` |
| 0x044000 | `critters_engine` | 0x083000 | `damage` |
| | | 0x086000 | `magic` |
| | | 0x087000 | `settings_foo` |

`tests/test_xbr_sections.py` checks every label against the file.
Until AZ-113 (2026-10-09) the labels were shifted by one table:
0x2000 was `armor_properties_real`, 0x4000 the "dead"
`armor_properties_unused` (it holds the attack animations; the engine
references `config/attacks_anims` at 0x7E301), 0x8000
`attacks_transitions`, 0x1A000 `critters_critter_data`, and so on to
0x87000 `magic`; 0x0 had no name (`tabl_17`), 0x83000 was
`critters_walking_dmg` in `keyed_tables`, and 0x86000 had none.

Old labels are not aliased and there is no migrator (owner decision
D43, 2026-10-09): an old-label config-mod fails loudly, naming the
edit. 4 old labels now name no table (`armor_properties_real`,
`armor_properties_unused`, `critters_walking_dmg` and `tabl_17`); the
other 13 now name a different table. No same-typed cell has the same
entity/property pair under a label's old and new table, except each
entity's `name` string, and every writer checks the cell type, so an
edit saved under an old label fails, with one exception:
`set_keyed_string <old label>/<entity>/name` renames the entity in the
label's new table without an error (e.g.
`critters_critter_data/garret4/name` now renames garret4 in the 0x8000
table).

AzurKit reads all 18 as keyed tables (`Document.tables`, `keyed.py`).
Modkit's document model read entries 15 (`damage`, 0x83000) and 16
(`magic`, 0x86000) through the variant schemas below instead.

### Table header

| Offset | Size | Field            | Notes |
|--------|------|------------------|-------|
| +0x00  | 4    | `num_rows`       | Property count. |
| +0x04  | 4    | `row_hdr_offset` | Always `0x10` in vanilla. |
| +0x08  | 4    | `num_cols`       | Entity count. |
| +0x0C  | 4    | `total_cells`    | `num_rows * num_cols`. |
| +0x10  | 4    | `cell_data_off`  | Cell-grid base = `table_base + cell_data_off + 0x10`.  In vanilla this always lands exactly at the end of the row-header array (`cell_data_off == 4 + 8 * num_rows`, 16/16 sections). |

### Row header record (8 bytes per row)

| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| +0     | 4    | `name_length` | u32 byte length of the row-name string, excluding the NUL.  Verified `== len(row_name)` on all 364 rows of vanilla config.xbr.  A row-name rewrite must patch this field. |
| +4     | 4    | `name_ref` | **Self-relative** u32: string address = `row_entry + 4 + name_ref`. |

Mirrors the type-2 cell layout exactly (`string_length` at +8,
`string_ref` at +12).

### Duplicate entity names

Column names are **not unique**.  Vanilla config.xbr repeats them
inside a single table — `critters_flocking` has two `good_noreht`
columns, `critters_maya_stuff` six duplicated pairs.  The canonical
resolution rule is **last match wins**: `Table.column`
([`keyed.py`](../src/azurkit/core/xbr/keyed.py)) takes the last
column of that name, for reads and writes alike.  To edit an earlier
duplicate, pass its column index: `Table.find(entity, prop, col)` and a
mods file's `set` with `"col"` match only when column `col` carries
that name (a stale index is refused by name).  Which duplicate the game reads differs by table (V20,
`RE_DATA.md` § Duplicate column names): `critters_flocking`'s loader
keeps the last, `critters_maya_stuff` is never loaded, and
`critters_mutate` reads both.

### Cell record (16 bytes per cell)

Cells are laid out column-major: column `c`, row `r` lives at
`cell_base + (num_rows * c + r) * 16`.

| Offset | Size | Type     | Usage                                        |
|--------|------|----------|----------------------------------------------|
| +0     | 4    | u32      | **type code**: 0 empty, 1 double, 2 string.  |
| +4     | 4    | u32      | padding (zero).                              |
| +8     | 8    | variant  | Type-1: IEEE-754 double.  Type-2: see below. |

For **type-2** cells the `+8..+16` payload is:

| Offset | Size | Field           | Notes |
|--------|------|-----------------|-------|
| +8     | 4    | `string_length` | Length in bytes, excluding NUL. |
| +12    | 4    | `string_ref`    | **Self-relative** u32: string address = `cell + 12 + string_ref`. |

### Pointer graph

For every keyed-table section:

- One `SelfRelativeRef` per row (source = row_entry + 4, origin =
  row_entry + 4).
- One `SelfRelativeRef` per type-2 cell (source = cell + 12, origin
  = cell + 12).

Both ref types are modeled in
[`src/azurkit/core/xbr/keyed.py`](../src/azurkit/core/xbr/keyed.py).  The pointer
graph walks them to answer structural-edit queries ("if I grow this
string by N bytes, which fields need patching?").

---

## Variant-record sections (2 TOC entries + 1 synthesised)

Modkit's document model read three tables a second way, as
fixed-stride records; AzurKit reads all of them as keyed tables, and
this section keeps that reading as a record of the bytes.
`critters_walking` and `damage` are TOC entries, matched on their
stored offset.  `settings_foo` is **not** — its `section_offset`
(0x88300) matches no TOC entry, so Modkit's
`XbrDocument.variant_sections()` reached it via a schema-offset
fallback that synthesised a free-floating overlay.

All three read keyed tables as fixed-stride records (AZ-113):
`critters_walking`'s TOC entry (0x83000) is the `damage` table and its
records start inside it (Step 1.23 retired its registry entries);
`damage`'s records lie in the `damage` table but its TOC entry (0x86000)
is `magic`; `settings_foo`'s records lie in the `settings_foo` table.

Fixed-stride record arrays; the schemas are only in
[`src/azurkit/core/xbr/keyed.py`](../src/azurkit/core/xbr/keyed.py)
(`config.keyed_tables` reads every table as a keyed table).

### Record layout

Per entity block: `props_per_entity * record_size` bytes.
Per property record: a leading prefix (0 or 16 bytes depending on
`record_size`), then `u32 type_flag` + `double value`.

| Schema              | `record_size` | `props_per_entity` | `entity_count` |
|---------------------|---------------|--------------------|----------------|
| `critters_walking`  | 16            | 18                 | 107            |
| `damage`            | 16            | 8                  | 11             |
| `settings_foo`      | 48            | 6                  | 1              |

### Pointer graph

No ref fields are currently reversed for variant records.  Edits
that change a record's stride would need additional RE — and in
fact Modkit's document model was **read-only** for variant records.
AzurKit reads these tables as keyed tables like the rest
(`src/azurkit/core/xbr/keyed.py`) and edits their cells by config.xbr's
own table / column / row names
([`src/azurkit/core/xbr/edits.py`](../src/azurkit/core/xbr/edits.py)),
for every host's builds alike.

---

## `indx` payload (index.xbr)

A u32 record count (3072), then an i32 pointer, relative to its own
field, to the record table at payload+8; 3072 records of 20 bytes,
sorted and unique by key, then the strings:

| Offset | Type | Field |
|---|---|---|
| +0 | u32 | key length (no NUL) |
| +4 | i32 | key pointer, relative to its own field |
| +8 | u32 | archive-name length |
| +12 | i32 | archive-name pointer, relative to its own field |
| +16 | char[4] | fourcc |

Every record repeats a row of its archive's named-resource table
(§ "The trailer"); no record holds a TOC index [verified 2026-10-11:
`tests/test_index_xbr.py::VanillaIndex::test_index_records_resolve_to_each_archives_named_resource`;
HM-03].  `IndexRecordsSection` frames the table (`count`,
`record_offset(i)`) and yields no refs, so structural edits raise and
the protected graph snapshot has none for index.xbr (Q242's default);
[`index_xbr.py`](../src/azurkit/tools/characters/index_xbr.py) decodes the
records.  [`RE_DATA.md`](RE_DATA.md) § "index.xbr" has the tag counts.

Until AZ-218 (2026-10-11) both read a 16-byte header (`count`,
`version` 4, `header_hint` 24, `pool_hint` 0xEFFC) and a record at
payload+16: those words were the count, the table pointer, record 0's
key length and its key pointer, and every field after them was
another one.  (Until AZ-124 the section unpacked at the bare stored
offset 0 and decoded the file header, `count=0x786F6278` (`'xobx'`).)

---

## Level node graph (`node`, `ndbg`, `levl`)

A level's logic is data: the `node` section is the level's exported
Maya scene graph of typed nodes (`transform`, `platform`,
`critterGenerator`, `switch`, `combiner`, `gameState`, `levelSwitch`,
`gameSaveControl`, `playerLocation`, …) wired by connections.  The
randomizer plan's census decoded it [verified 2026-10-10 by a
consistent decode of every level: the census and its decoders, private
evidence outside git].  The structure
below, and its counts, were re-read on the vanilla ISO with
`toc_scan.parse_toc` on 2026-10-10, counts only [verified]; what that
re-read did not check is marked [census].  The document model still
reads these sections as `RawSection`; `src/azurkit/core/xbr/nodes.py` reads
them for the randomizer's `rando db-extract` and the player-model swap
(Step R1.1).

- **Which files.** The 33 level XBRs (the files with a `levl` entry)
  hold 37 `node` sections; `characters.xbr` and `fx.xbr` have more:
  263 on the disc.
- **`node` payload.** A u32 record count at +0, then at +4 a
  self-relative u32 to a table of `count` self-relative u32 pointers,
  one per record (0 = none).  +0x0C/+0x10 is the **save list**: a count
  and a self-relative ref to that many u32 record indexes, the nodes a
  level `.sav` restores, in that order ([`SAVE_FORMAT.md`](SAVE_FORMAT.md)
  § 4d); +0x14/+0x18 is a third list, record indexes too: in the 226 fx
  graphs 44 timers and one switch in 44 graphs, none a DAG root, so an
  auto-run list [inferred; data: Step 2.157's design, `census_third`]
  [verified static: the node-graph initialiser 0x65E50, the randomizer
  R0's `wiring/REPORT.md` §1].  Every DAG record's parent comes before
  it: 8,358 of 8,358 in the 226 fx graphs [data: Step 2.157].  The u32 at +0x1C is the TOC index of
  the graph's `ndbg`, a relocated field (§ "The trailer"): 263 of 263
  name an `ndbg` with the same record count [verified 2026-10-11;
  HM-07].  Pairing each `node` with the nearest `ndbg` before it in
  the TOC (Level Studio's rule, and this section's until Step 2.16l)
  is wrong in 16 of the 263, all in `characters.xbr` and `fx.xbr`.
- **`ndbg` payload.** +0/+4: (length, ref) → the source scene's path;
  +8: the record count; +12: a self-relative ref to a table of
  self-relative pointers, entry i to a 16-byte record whose +0/+4 is
  the (length, ref) name of node record i (all 67,560 level records
  have one) [verified 2026-10-11].
- **Record header.**
  - +0x00: (length, self-relative ref) → the type name.  All 67,560
    records in the 33 level files have one; there are 39 distinct
    types there and 40 on the disc (`transform` 40,860, `platform`
    11,220, `light` 488, `playerLocation` 227, `levelSwitch` 124)
    [verified 2026-10-11].
  - +0x08: (count, ref) → the attribute block, which lies inside the
    section for every record; its values are f32 and what each holds
    depends on the type [census].  The count is fixed per type:
    `transform` and `joint` 10, `platform` 37, `light` 10, `lod` 21,
    `critterGenerator` 14, `levelSwitch` 1, `pEmitter` 18, `shader` 64,
    `effect` 34 [verified 2026-10-11, every node section].
  - +0x10: (count, ref) → outgoing connections, 24 bytes each, with
    the destination record's index at +0x14.  7,852 records have
    some, 26,623 in all (1,030 of them on 518 `transform` records),
    and every one points at a record of the same section.  A link is
    `{f32 weight +0x00, u32 curve +0x04, f32 factor +0x08, u16 source
    plug +0x0C, u16 target plug +0x10, u32 target record +0x14}`; a
    plug indexes the attribute list of its record's type (§ "Links,
    curves and logic nodes" below) [verified static: the link loader
    0x658F0 steps 0x18 (0x65975) and reads both plugs as u16 (0x65950,
    0x65956); verified 2026-10-12: the high halves at +0x0E/+0x12 are 0
    on all 31,919 links in the disc's 263 `node` sections, and no plug
    is outside its type's list (`src/azurkit/core/xbr/nodes.py`; Step
    R1.1's docs script, counts only)].
  - +0x18: a parent index, but only on spatial and DAG types
    (`transform`, `joint`, `lod` …): `levelSwitch` keeps its movie
    string there, and `gameState` (length, ref) pairs start there
    [hub verifier and census, HM-07].
- **`critterGenerator`.** Every placed pickup and every critter
  (enemies, gems, keys, fragments, powers) is one: 3,129 in the level
  files.  +0x1C names the critter (3,124 of them; the other 5 have an
  empty name).  The name is a pooled string: every generator of one
  critter type in a `node` section points at the same one (397 such
  pairs, no exception), so renaming it in place retypes them all
  (census F1).  +0x2C is (count, ref) of its gen points, 12 bytes
  each; +0x34 indexes the level's cell list.  The
  engine's generator code reads a count at the same +0x2C, with
  12-byte points (`RE_XBE.md` § "Level node graph: the engine side").
- **What `find_level_entities` finds** (AZ-240) [verified 2026-10-11 on
  the 22 `LEVEL_XBRS`, counts only: AZ-240's finder-versus-nodes
  script and its README, which states each rule].  The randomizer's byte
  heuristic (a 1.0f, a printable name, then (x, y, z, 0) at one of four
  fixed offsets before it), which `level_patches` moves and renames use,
  finds 502 names.  336 are a `critterGenerator`'s +0x1C name string.
  For 331 of them the 12 bytes a move writes are attributes 1–3 (T) of
  the transform that is the parent (+0x18, a `transform` index in all
  3,114 generators of those files) of the first generator of that name
  in table order; no other generator of the name shares that transform.
  The other 5 are logic data: training_room's four `large_*_fuel` land
  on a `combiner`'s attributes 9–11, and d1's `key_diamondbattery` on a
  `randomNumber`'s link 0 target and the 8 bytes after its one link (a
  `soundEffect`'s attributes 0–1).  The 166 names that are not critter
  names land on other records' attributes or links, between blocks, or
  (19) outside the `node` sections.  Only 132 of the 331 have every
  ancestor exactly the identity, and the transform's own pivots and the
  generator's gen points all zero (the README's rule 3).  That the
  stored T is the spawn points' world position for those 132 and not
  for the rest rests on HM-08's composition (a hub PAL reading; the
  `transform` bullet below) [inferred].
- **`gameSaveControl`.** The save points: 43 in 22 levels, each with
  its save id string at +0x1C ([`SAVE_FORMAT.md`](SAVE_FORMAT.md)
  § 4e).
- **`levelSwitch`.** 124 in the level files.  +0x18 holds a movie
  (`bink:…` or `movies/scenes/…`, often empty), +0x20 the destination
  and +0x28 the spot, all (length, ref) strings [verified 2026-10-11;
  HM-09].  74 of
  them, all in the 22 playable levels (the census's realm, hub and
  boss levels), name a `levels/...` destination and a spot.  Of the
  other 50, 36 also name a `levels/...` path (33 in the developer
  `selector`, 3 in cutscene levels), 10 name another string (one of
  them in `d1`) and 4 have an empty one (2 in `selector`, 1 each in
  `diskreplace_air` and `diskreplace_life`).  Exits from one level to
  the same destination
  share one string (the 74 form 50 such pairs; 16 of them, with 40
  exits, have more than one), so an in-place rewrite moves them all
  (census F2).  The named switches the loading-zone catalogue once
  called "implicit, no destination" point at such shared strings
  (AZ-221; [`RE_DATA.md`](RE_DATA.md) § "Level loading").
- **`platform`.** Barriers, geodes, keylock triggers and crystals are
  platforms whose data block starts with a damage fourcc (`watr`,
  `stem`, `acid`, `wind`, `fire`, `litn`, `ice`, `smsh`, `none`); these
  are the bytes the old randomizer's barrier shuffle rewrote (retired
  at Step R1.10b) [census, not re-checked here].
- **`transform`, `joint`, `lod` (per Level Studio).** Attributes:
  visibility, T xyz, Euler R xyz (radians), S xyz.  +0x28 inherit mode
  (0 normal, 1 drops parent orientation and scale, 2 keeps only the
  yaw about world Z, 3 camera-facing); +0x2C scale pivot, +0x38 its
  translation, +0x44 rotate pivot, +0x50 its translation; +0x5C an
  orientation quaternion; +0x6C rotation order 0–5.  World matrix:
  T·Trpt·Trp·R(order)·Trp⁻¹·Tspt·Tsp·S·Tsp⁻¹ (Maya's).  [inferred: PAL
  per Level Studio; the hub's own composition reproduced its 30 w1
  fixture nodes to 5.5e-6 on USA data, HM-08.]  Mode 2 implies Z is up
  [inferred].  Not every record is mode 0 / order 0: e2, e5, e6, e7
  and d1 use modes 1–3, e2/e5/e6 order 3, and a3 and characters have
  mode-7 records, outside 0–3 [hub verifier].  **On USA**
  `src/azurkit/core/xbr/nodes.py` composes it the engine's way [verified
  static: the loader 0x67F80, the local-matrix builder 0x68BE0 (vtable
  0x19D390 slot 16) and the Euler routine 0xBC630; R0's `r0/PREP.md`
  §3.4]: the local matrix (column vectors) is
  T(t + rpt + rp)·R(order)·T(spt + sp − rp)·S(s)·T(−sp), with t/r/s
  attributes 1–3/4–6/7–9, sp +0x2C, spt +0x38, rp +0x44, rpt +0x50.
  R is Shoemake's Euler matrix in the static frame, its axis and parity
  tables read from 0x1979D0 and 0x197A18, so orders 0–5 are xyz, yzx,
  zxy, zyx, yxz, xzy (orders 3 and 5 are swapped against Maya's
  `rotateOrder`).  The +0x5C quaternion is not read there.  Inherit
  modes (0x681E0, jump table 0x68BBC): 0 and 6 compose normally (P·L);
  1 replaces the parent by the translation T(P·a − a), a = t + rp; 2
  (0x68359, Step X.16) by an upright frame: P's quaternion q (0xA0520,
  Shoemake's, on P as it is) composed as q·r with r the shortest arc
  from world up to world up in q's frame (q's matrix's third row), so
  the frame turns about world Z only, and the translation P·a − R'·a
  that keeps a where P puts it (P's scale is dropped; under a scaled
  parent the frame is skewed, not level); 3 (0x6880A, Step 2.157) keeps
  the anchor a where P puts it (P·a) and takes its axes from the top
  camera's quaternion (`[[node+4]+0x44]+0xA8` is a vector of cameras, the
  last one's vtable +0x34; the identity when empty), scaled by the length
  of P's first row, then composes the local matrix as mode 0 does: a
  node facing the camera (the game's shields: a hemisphere that reads as
  a sphere from every side) [static: Step 2.157's disassembly of 0x6880A's mode 3;
  its skeptic reads the world translation as P·V − s·R_cam·V, V the
  node's pivot (`[[node+8]+4..+0xC]` + `[node+0xC8..0xD0]`), so a
  translate enters both frames; which fields hold translateXYZ is
  unread]. Put a mode-3 node's height in its parent, not its own
  translate [observed xemu, sitting 2.157: beamlord's shield at
  translateZ 1.05 under effectOrigin drew round his feet, not raised;
  translateY −0.7 under spine_2 moved it up and aside on screen];
  4, 5, 7 and 8 are not decoded, and `nodes.py` composes 3-5, 7 and 8
  like mode 0 and marks the result approximate (the camera isn't known
  offline; 3, 4, 5, 7 and 8 set the engine's per-frame flag 0x40000000).
  +0x70/+0x74 is a (count, self-relative ref) list whose count equals
  the record's child count in all 5,472 fx transforms; the loader
  0x67F80 links children at run time (child+0x1C, parent+0x20), so it
  looks unread [data, static: Step 2.157's critique].  Mode 2 is checked against the
  game's own 0x68BE0 and 0x681E0 under Unicorn
  (`devkit/sim/l2.py` `transform_world`): every one of the 292
  transforms with mode 2 in its chain (e2, e5, e7) to 7e-7 relative,
  so e5's 152, e2's 20 and e7's 10 platforms on upright carriers are no
  longer approximate.  It reproduces Level Studio's 30 w1
  fixture matrices to 5.5e-6; the census decoder it replaced swapped
  the pivots and dropped their translations, missing them by up to
  ~859 units in w1 (HM-08), and the fix Phase R1's port owed before it
  read positions (R1.1–R1.3, D137; *was:* Step 4.10a) is this reader
  [workflow: R0 PREP §3.4's `check_transforms.py` run, 2026-10-11].
- **`light` and `platform` (per Level Studio, PAL).** `light`: +0x1C
  type 0–3 (ambient, directional, point, spot), falloff 0–2 and exclude
  bytes, +0x20 a u16 id; attributes 4–6 RGB, 7 intensity (negative
  flips the colour), 8 cone, 9 penumbra; a cell selects at most 4
  lights.  `platform`: +0x1C count and +0x20 ref of 72-byte type-5
  descriptors (§ "`levl`"; a descriptor's +0x30/+0x34 lists one 24-byte
  sub-bounds block at +72, its bounds again, in all 1,155 fx
  descriptors); +0x24 its `tern` (relocated; -1 none); +0x28/+0x2C and
  +0x30/+0x34 two (length, self-relative) strings, 'all' (or 'player')
  and 'player' in all 1,190 fx platforms, the first the class the
  platform loader parses (0x6A920 into 0x50D80, against the table at
  0x1A9E68: none, all, tiny, small, ...; an unknown token sets bit 31)
  [static, data: Step 2.157's critique]; attribute 10 (`gameVisible`) scales
  opacity and 24 (`MeshOffset`) biases the sort distance only (USA
  strings 0x199EE8, 0x199E64) [hub, PAL; only the attribute counts
  are verified on USA].
- **Particles, trails and effects** (Step 2.167a: each type's loader,
  slots 1 and 2 of the vtable its factory in 0x721B0's table installs;
  every value checked on the 226 fx graphs [static, data: Step
  2.167a's reads].  A `pSystem` (64
  bytes) holds +0x1C its pool size (1-5000), +0x20 its renderer's record
  index (a `pRendererB` in all 421), +0x24 an f32, +0x28/+0x2C a (count,
  self-relative) list of u16 cell indices (empty in all 421) and
  +0x30/+0x34 a list of u32 record indices, its components (emitters,
  sinks and forces: every one a `pComponent`, 1,701 in all; 0x6C210);
  a `pBurstEmitter` (36 bytes) +0x1C/+0x20 a list of u32 record indices,
  the targets its bolts reach (135 `pNull`s, 2 `pEmitter`s; 0x6D580).
  The components (`pEmitter`, `pSink`, `pBoxSink`, `pAccelerator`,
  `pGravity`, `pVortex`, `pNull`) hold only their parent (+0x18); a
  `pRendererB` (32 bytes) its texture at +0x18 (relocated) and -1 at
  +0x1C.  A `polyTrail` (44 bytes): +0x1C a relocated `gshd` and +0x20
  its row (0x7C443), +0x24/+0x28 a u16 cell list (empty in all 50).  An
  `effect` (0x707D0): +0x1C/+0x20 the (length, ref) key of the graph it
  loads and +0x24 a u16 cell (0xFFFF, the instance's, in all 12).  A
  `timer` reads nothing past the header (0x658E0), a `combiner` +0x18 its
  input count and +0x1C its function (0x69BF0).  No two lists share
  storage, and no fx graph has a save list.

### Links, curves and logic nodes

The logic of a level is its links: the randomizer's R0 decoded them
(its wiring report, §1–§2, and thresholds report, §1, §11; the engine's
VAs are in
[`RE_XBE.md`](RE_XBE.md) § "Level node graph: the engine side"), and
`src/azurkit/tools/randomizer/levels.py` reads them for `rando db-extract`.
Labels are the reports' unless marked.

- **Attribute names.** `default.xbe` registers 44 node types, each
  with its attribute names, defaults and parent type; a record's
  attribute block (+0x08) has exactly its type's count, its ancestors'
  attributes first (`critterGenerator`: `lodVisibility`,
  `localPositionX`..`Z`, `g2g`, `playAnimIndex`, `numGenerated`,
  `numAlive`, `numDead`, `maxGenerated`, `maxAlive`, `critterRange`,
  `emitDelay`, `enable`) [verified 2026-10-12: `nodes.Schema` reads 44
  types; every one of the disc's 78,155 records has a registered type
  and exactly its type's attribute count].
- **Propagation.** Every frame, for each node marked dirty, the engine
  runs its update and then sets each link's target attribute to
  `curve(source × weight) × factor` (the curve skipped when the link
  has none), marking the target dirty when the value changes; every
  node starts dirty, so derived state recomputes after a load
  [verified static: 0x663B0; the start-dirty store at 0x7371A].
- **Curves.** The curve word 1 means no curve; anything else is a
  self-relative ref from the curve field to a header `{u16 pre,
  u16 post, u32 n (low 28 bits), i32 ref}` and n keys `{f32 x, y,
  inTan, outTan}`.  Below the first key the pre mode applies, at or
  past the last the post mode (0 constant, 1 linear, 2 cycle, 3 cycle
  with offset, 4 oscillate); inside [x_i, x_i+1) an outTan above
  FLT_MAX holds y_i (a step), else the segment is a cubic Hermite with
  m0 = dx·outTan_i and m1 = dx·inTan_i+1 [verified static, lane: the
  copy 0xD87E0 and the evaluator 0xD8300].  The seal, obsidian-lock and
  barrier thresholds are curve keys, not node constants.  19,928 of
  the disc's 31,919 links have a curve [verified 2026-10-12].
- **`combiner`.** Record +0x18 is the input count n and +0x1C the
  function code; attributes `inputs[0]`..`inputs[15]`, `index` (16,
  clamped to [0, n−1]) and `output` (17).  All n inputs are read,
  linked or not: an unlinked input keeps its stored value.  Codes: 1
  sum, 2 in0 − Σrest, 3 product, 4 max, 5 min, 6 the first non-zero
  input's value, 7 and (1/0), 8 xor, 9 not, 10 in[index], 12 nand, 13
  nor, 14 xnor; 11 and 15 are not decoded [verified static, lane:
  0x69BF0, 0x69C10, jump table 0x6A008].  Codes 2, 9, 11 and 15 occur
  nowhere on the disc.  The 23 randomizer levels hold
  1,601: code 1 ×25, 3 ×278, 4 ×49, 5 ×1, 6 ×283, 7 ×429, 8 ×10, 10
  ×210, 12 ×296, 13 ×17, 14 ×3 [verified 2026-10-12].  Read the code,
  never the name: ten combiners' names contradict it (d1's
  `SealCheck_nandCombiner` is a nor, w2's `andCombiner2`–`7` are ors).
- **`switch`.** Attributes `pause`, `turnOn`, `turnOff`, `toggle`,
  `lock`, `onTime`, `offTime`, `output`, `goal`.  Unless `pause` is
  set, a non-zero `turnOn` sets the goal to 1, else `turnOff` sets it
  to 0, else a toggle flips it; `lock` makes it ignore inputs until
  `output` reaches `goal` (it is not a latch); `output` ramps toward
  `goal` by (1/30)/onTime or (1/30)/offTime per tick.  So a switch
  with no `turnOff` or `toggle` input is a one-way latch, and a stored
  non-zero `turnOff` with no link makes it follow `turnOn` [verified
  static, lane: 0x6A0F0; the 1/30 at 0x1981E0].  Whether a switch
  persists is only whether the save list holds it.
- **`gameState`.** Ten value slots (`value0`..`value9`), each named by
  a (length, ref) string at record +0x18 + 8k that the engine looks
  up, case-insensitively, in the XBE's 31-name table
  ([`RE_XBE.md`](RE_XBE.md)); every update re-reads them all from the
  inventory and marks the node dirty again [verified static: 0x71160,
  0x711C0, 0x714FB].  Every variable is an integer except `day night
  timer` (the fraction of the clock, [0, 1)) and `armor fraction` (the
  armor gauge), so a link's condition is a set of integers, or of
  intervals for those two.
- **`latch`.** Attributes `input`, `update`, `output`: while `update`
  is non-zero, `output` follows `input`.  A non-empty (length, ref)
  name at record +0x18 binds the latch to a **global** of that name,
  the map `shared.sav` holds ([`SAVE_FORMAT.md`](SAVE_FORMAT.md) § 4b),
  so named latches carry state between levels: 62 of the 69 latches in
  the 23 levels bind 29 names (`AirRealm_fixed`, `conveyor_on`,
  `W4_Crane` …) [verified static: 0x6A2E0, 0x6A350, 0x5E690; verified
  2026-10-12: the committed generated data].
- **`platform` fields** [verified static: the platform loader 0x6A490,
  lane; +0x30–+0x44 re-read]: +0x18 parent; +0x1C/+0x20 the descriptors
  and +0x24 an index (§ "`levl`"); +0x28/+0x2C and +0x30/+0x34 two
  strings (`all` …, `player`); +0x38/+0x3C the damage string, turned
  into a fourcc (0xB62F0); +0x40 the **key fourcc** (`a1k1`,
  `e7k1` …, `critters_item_data`'s `invType` of a key; 39 platforms in
  the 23 levels carry one [verified 2026-10-12]), or `open`, which sets
  `key` (attribute 23) to 1 at load; +0x44 another fourcc.  A hit whose
  damage fourcc equals the platform's sets `magic` (attribute 4) to an
  integer the attack carries, which a barrier's `magic` links then
  read; that the integer is the attack's power level is [inferred]
  (0x79F80, event 3).  `whack`, `magic` and `touch` are pulses: 0x7A280
  resets them, each frame [inferred].
- **`critterGenerator` fields** [verified static, lane: the loader
  0x6F570]: +0x18 parent; +0x1C/+0x20 the critter name, used as
  `name[:N]` (a name starting `AICookie/` makes an AI cookie, not a
  critter); +0x24/+0x28 an optional comma-separated list; +0x2C/+0x30
  the gen points, 12 bytes each; +0x34 the cell, a u16 (0xFFFF: the
  default).  Its spawn budget per tick is `min(maxGenerated −
  numGenerated, maxAlive − numAlive)` while `enable` is non-zero, a
  negative limit −N meaning N × the point count and 0 meaning no limit
  (0x6FD40, the negative branch re-read).

Structural edits stay unsupported.  Whether the engine accepts a ref
into the alignment gap after a section was open until the R0
sittings: it does read a name string placed in the gap after a `node`
payload once that entry's TOC size grows over it: a generator
repointed to such a string spawned its item in xemu, up to 1,024 B
into w1's 4,088 B gap, and (Step R1.10a) up to the gap's last byte, in
w1 and in town's second graph, so the whole gap is usable.  With the
TOC size unchanged it reads only up
to the next 512-byte boundary, 93–504 B per graph, because the loader
rounds the read length up to 512 [verified xemu, placed, and static:
sitting rz-c, I-5 (b1), (b2); the whole gap: sitting r110a].

### `levl`

[verified 2026-10-11, all 33 `levl` entries; HM-10]  Self-relative refs
throughout:

- **Header.** +0x0C..+0x14: the sky anchor, 3 floats in centimetres
  (finite in all 33); +0x1A: a u16 sky cell, 0xFFFF for none (set and
  a valid cell in 29); +0x1C/+0x20: count and ref of 72-byte cells;
  +0x2C/+0x30: count and ref of 72-byte static descriptors.
- **Cell.** +0/+4: its (length, ref) name; +64/+68: count and ref of
  its light ids.  264 cells on the disc (e2 has 32, f3 31), all named
  in ASCII, 1,020 light ids.
- **Static descriptor** (world geometry; node platforms use the same
  one).  u32 flags; six float bounds at +4; type 5 at +28; cells
  +32/+36; light refs +40/+44; sub-bounds +48/+52; per-part lights
  +56/+60; LOD pairs +64/+68, 16 bytes each (`rdms`, `pbrc`/`pbrw`,
  fourcc, max distance), distances non-decreasing.  16,074 on the
  disc, all type 5; 505 have more than one LOD pair.

### `tern` (collision)

The `tern` sections are the collision meshes; the visible meshes are
`rdms` (§ "Graphics resources").  [verified 2026-10-11 by the
randomizer evidence's `tern` reader, re-run for Step 2.20j, counts
only, outside git (D110).  Its `selfcheck` parses every `tern` on the disc
(34 files, 5,976 sections, 126,511 chunks, 4,630,337 vertices,
4,419,456 triangles) with 0 layout violations; its `s6check` compares
them with xemu session s6's captures.]  Since Step R1.2
`src/azurkit/tools/randomizer/art/tern.py` reads it (`parse`, and `census` for those
counts, which `tests/test_collision_mesh.py` pins on the vanilla disc
[verified 2026-10-12]); the document model still keeps it as
`RawSection`.  Azurik Level
Studio's "collision" overlay reads `sdsr` (streamed audio, HM-12) and
finds no faces on the USA disc (the Level Studio run under D104,
§3.1).

- **Owners.**  Every `tern` is referenced exactly once (the
  relocation table's `levl` → `tern` and `node` → `tern` rows):
  - 29 by a `levl` payload's +0x00, a u32 TOC index: the level's
    static world collision, in world coordinates;
  - 5,947 by a `platform` record's +0x24, an i32 TOC index (−1 =
    none): the platform's collision, in its local frame, placed by
    its world matrix.

  Since Step R1.3a `src/azurkit/tools/randomizer/art/collision.py` reads each level's
  owners (`owners`): the static mesh with its chunks' flags, and each
  platform with its world matrix (`nodes.Graph.world`) and the
  collision word its attributes give (`platform_word`, the bits in
  [`RE_XBE.md`](RE_XBE.md) § "Collision (`tern`): the engine side").  A
  second reference to one `tern`, or a reference to an entry that is
  not a `tern`, fails the load.
- **Section.**  +0: u32 n, the chunk count (≥ 1).  +4: an i32 that is
  self-relative from +4 and points at the spatial structure.  From +8:
  n u32 chunk offsets from the section start, the first 8 + 4n,
  ascending and 4-aligned.  After the last chunk come 0–2 bytes of
  padding, one u32 and the spatial structure, which runs to the end of
  the section (a median of 40 bytes per chunk).  Neither the u32 nor
  the spatial structure is decoded.
- **Chunk.**  A 22-byte header, then the vertices and faces:

  | Offset | Field |
  |---|---|
  | +0 | i16 ×3, min: whole metres, the floor of the lowest vertex |
  | +6 | u8, vertex count (≥ 1) |
  | +7 | u8, face count (≥ 1) |
  | +8 | i16 ×3, max: whole metres, the ceiling of the highest vertex |
  | +14 | i16 ×3, centre: whole metres, inside [min, max] |
  | +20 | u16, flags: the chunk's collision class |
  | +22 | the vertices, i16 ×3 each; a vertex is centre + v / 256 metres (the same 1/256 m quantum as `rdms`) |
  | then | the faces, 4 bytes each: three vertex indices (each below the vertex count) and a group byte: the faces are sorted by their first vertex's x (the face's least x), and the group byte is the lowest face index whose largest x reaches this face's least x, a sweep-and-prune back-pointer the engine's chunk walk (0xD18D0/0xD19B0) uses to cut a chunk to a query's x range (non-decreasing within the chunk; 673,818 of 673,818 faces and 20,318 of 20,318 chunks on e7, a5, f2 and w1: Step R2.17's collision map, landed with Step R2.19d) |
  | then | 0 or 2 bytes of padding to the next 4-aligned chunk |

- **Flags.**  Every platform-owned chunk has 0xC000 (22,896 chunks):
  the platform's attributes give its collision bits ([`RE_XBE.md`](RE_XBE.md)
  § "Collision (`tern`): the engine side").  Static chunks have
  0x8050 (92,326 chunks, 3,319,263 triangles), 0x8051 (10,998;
  382,817), 0x8052 (204; 8,562) or 0x8013 (87; 2,710).  Read with
  the platform builder's bits, these are solid, slippery, climbable
  and one exception that is all three without bit 0x40 [inferred,
  strong].  10.3 % of the floor-like static triangles (|normal z| ≥
  0.7071) are slippery.
- **Checks against xemu** (`s6check`).  Six standing spots in s6's
  captures lie on a `tern` face, each within 3e-6 m.  f6's ledge is
  1.2578 m high in `tern` and in xemu (error 1.2e-5 m).  At both
  landings in s6's w1 airtime capture, the low 16 bits of the
  player's contact word equal the flags of the chunk under the player,
  0x8050.
- **Level Studio's reading.**  Its run found the vertex part of this
  layout in platform `tern`s and called it an 8-byte header and a
  vertex block (REPORT §3.2).  That is the chunk header split at +8,
  so its "+12 is 0xC000" is the flags at +20 [inferred].  The faces
  and the static chunks are new with the reader.

---

## Graphics resources (`surf`, `rdms`, `gshd`, `pbrc`/`pbrw`, `body`/`bmsh`)

From Azurik Level Studio's readers (MIT, knowledge only; HM-11).  Since
Step 2.33 `src/azurkit/tools/randomizer/art/render.py` reads textures, materials, meshes,
push buffers, the `levl` static descriptors and a platform's render
descriptors (record +0x1C count, +0x20 ref), for the randomizer's level
maps (`src/azurkit/tools/randomizer/art/maps.py`); the document model
keeps them as raw payloads.

- **`surf`** (textures) [verified 2026-10-11, all 10,508]: the u32 at
  +0 is 1 for an animated list of frame `surf` indices (212), else a
  type whose low 16 bits are the format, 0x10 BGRA8 (249), 0x20 DXT1
  (7,357) or 0x40 DXT3 (2,690), with bit 28 for a mip chain (10,251)
  and bit 29 for a cube map (14).  Per Level Studio: float width and
  height at +28/+32, self-relative pixel pointers at +40..+60 [hub].
  It is not "triangle / material data", as this doc's backlog once
  said.  Every texture of characters.xbr and fx.xbr has a header that
  three numbers give [verified 2026-10-22, Step 2.157: all 1,490]: +0
  the format | bit 28, +4 0x40001, +28/+32 the size, +40 the i32 88 (the
  texels at +128), every other byte 0; the texels are each level down
  to 1x1 (a DXT level at least one 4x4 block), and a square one's TOC
  size is exactly that, 128-aligned (1,467 of 1,467; the 23 non-square
  ones' chain rule is unread).  A list is +4 the frame count, +8 the
  i32 4 (a self-relative pointer to +12) and +12 the frame indices, each
  a relocated field: 12 + 4 x frames bytes (77 of 77).  The frame rate is
  not in the list; where a graph has a `shader` node, its
  `textureNFrameRate` drives it [inferred] (Step 2.157; `docs/RE_DATA.md`
  § "fx clones").  The shader's update (0x71E30) copies six attributes
  of each stage into its material row's stage: CurrentFrame, FrameRate,
  Scale, Rotation, TranslateU, TranslateV to the stage's +0x14, +0x10,
  +0x20, +0x24, +0x28, +0x2C; the two attributes named `texture1URate`
  are never copied [static, Step 2.155e's design]; a row no shader
  updates keeps its stored stage (spideyzar's blast dome, gshd 267 row 2:
  a 5-frame list at 20 a second, scale 1).
  [`textures.py`](../src/azurkit/tools/characters/textures.py) writes both (Step
  2.157, D362: Level Studio's BC1/BC2 encoder, ported).
- **`rdms`** (meshes) [hub verifier, HM-11]: magic 5; +4 a `gshd`
  index (a relocation, § "The trailer"); +24 vertex count; +44 the
  vertex declaration; +52 a relative index table; vertices from +64,
  int16/256 positions plus an origin, CMP 11:11:10 normals, BGRA and
  UVs (declaration 0x252 is a float layout of stride 44, its positions
  also relative to the origin [verified 2026-10-13: w1's 47 such meshes
  fit their descriptors' bounds only so]; from stride 18 the UV is i16 /
  1024 at +14, 0x252's float UV at +28 [inferred 2026-10-14: the barrier
  meshes' textures map so, Step 2.52]).  All 28,547
  fit `align4(64 + n × stride)`; declarations 0x80002111 ×23,256,
  0x80001111 ×4,000, 0x252 ×835, 0x80004111 ×456.  The rest, as all
  1,155 meshes the fx graphs' platforms draw hold it (both fx archives,
  every LOD) [verified 2026-10-23, Step 2.155e:
  [`fx_mesh.py`](../src/azurkit/tools/characters/fx_mesh.py) reads and writes each
  back byte for byte, `tests/test_fx_mesh.py`]: +8 the material row;
  +12..+20 1, 0, 0 (a D3DVertexBuffer); +28 36 (a self-relative pointer
  to the vertices); +32 the origin, f32 ×3; +48 the part count, 1; the
  part table at `align4(64 + n × stride)`, per part a u32 index count and
  an i32 relative to its own field to a u16 triangle list, the payload
  ending with the last (unpadded); +56/+60 0; the part's triangles are
  the push buffer's strip's.  A normal is 11:11:10 signed, x in the low
  bits (/1023, /1023, /511); the vertex colour is BGRA (0, 0, 0, 255)
  in every one.
- **`gshd`** (materials) [hub verifier]: 100 + 124 × stages bytes:
  technique, colours, flags (0x20 double-sided, 0x10 MODULATE2X),
  opacity, alpha, blend and per-stage (`surf` index, `sprv` index, UV
  transform); 6,223 materials, all 8,632 stage textures `surf`.  Row +84
  is the alpha-test reference (0.1 in most rows) [inferred 2026-10-14: a
  key card's 8-vertex plate is cut to its key shape by its texture's
  alpha only so; Step 2.52].
- **`pbrc`/`pbrw`** [hub verifier]: NV2A push buffers using only the
  methods 0x17FC, 0x1800 and 0x1808 (22,721 and 5,826 parse).  An fx
  platform's (all 1,155) [verified 2026-10-23, Step 2.155e]: a 32-byte
  header (+0 the strip's index count less 2; +4 28, a self-relative
  pointer to the commands at +32; +8..+16 0; +20 and +24 the commands'
  size; +28 its own tag) and one strip in
  `body_codec.encode_strip`'s form; a `pbrc` up to 1,028 bytes in all
  (1,043), a `pbrw` past it (112); the LOD pair's fourcc is its tag.
- **`body`/`bmsh`** (characters) [hub verifier]: bone and LOD counts
  and per-LOD `bmsh` indices; `bmsh` groups of 40 bytes, FVF 0x1021C
  (all 694).  Since Step 2.52 `render.body_meshes` reads a body's most
  detailed LOD [verified 2026-10-14, USA: all 158 bodies, their 507 LOD-0
  groups]: `body` +0 the bone count, +8 the LOD count and +12 an i32
  relative to +12 to that many `bmsh` TOC indices, then LOD 0's 28-byte
  records, one per group (the full path is +16, the LOD count again, and
  +20, an i32 self-relative pointer to a (u32 count, i32 relative
  pointer) pair per LOD, which the draw reads at 0x3F154–0x3F178; LOD 0's
  records follow the `bmsh` list in 158/158 bodies, LOD 1+'s sit
  elsewhere in 80/80 [verified 2026-10-21, Step 2.130]): +0 an i32
  self-relative pointer to an NV2A push buffer of one triangle strip,
  ended by 0x17FC 0; +4 its triangle count, the strip's indices less 2;
  +8..+27 a D3DPushBuffer header (Common 0x10001, Data 0, Lock 0, Size =
  AllocationSize in the file; the draw fills it on first use,
  0x3F1C7–0x3F1DE).  `bmsh` +0 the group count
  and +4 an i32 relative to +4 to the groups: +4 the group's bone count
  and +8 an i32 self-relative pointer to that many i32 bone indices (the
  bones its vertices' +56 slot bytes index; the body draw loads each one's
  world matrix times its inverse bind, 0x3F2D2–0x3F34F and
  0xCC8B7–0xCC92D: Step 2.106, `characters.mesh_groups`), +24 the vertex
  count, +28 an i32 self-relative pointer to the 60-byte vertices
  (declaration 0x1A7C08: a float position, +12 four blend weights summing
  to 1, +28 the normal, +40 the UV, +48 an unused float pair (0 in all
  326,892 vertices of every LOD), +56 four bone-slot bytes, one per
  weight: byte b names palette entry b-1 for 1–12 and b-2 for 14–32, 13
  never, and slot 0 holds the heaviest weight), +32 the `gshd` and +36
  the row.  Every strip index is below its group's vertex
  count.

Level Studio edits same-size BGRA8/DXT1/DXT3 textures and
vertex-only mesh deformations in place (HM-15); W24 writes a variant's
LOD-0 positions and their fans' normals in place (Step 2.142,
`src/azurkit/tools/characters/mesh_edit.py`), and W29 a jiggle's weights, slot
bytes and freed palette entries (Step 2.143,
`src/azurkit/tools/characters/jiggle.py`).

**The whole layout, written back with any topology** (Step 2.154,
[`body_codec.py`](../src/azurkit/tools/characters/body_codec.py)) [verified
2026-10-22: all 158 bodies and their LODs' `bmsh` payloads decode and
encode back byte for byte, `tests/test_model_write.py`]:

- A `body` payload is its 0x20-byte header (+0 bones, +4 → the bone
  records, +8 LODs, +12 → the LOD list, +16 LODs again, +20 → a (group
  count, → records) pair per LOD, +0x18 markers, +0x1C → the marker
  records, or the pairs' place when there are none), then the 160-byte
  bone records (+0 the name's length, +4 → the name), the 0x38-byte
  marker records (+0 the length, +4 → the name), the pairs, the bone
  names and then the marker names (NUL-terminated, in order), zeros to a
  4-byte boundary, the LOD list (relocated), and per LOD its 28-byte group
  records followed by its groups' push buffers, each Size bytes, back to
  back.
- A group's push buffer is BEGIN `0x17FC` = 6, its strip's indices as
  `0x40001800` commands of at most 256 dwords and, for an odd count, one
  `0x1808` dword last, END `0x17FC` = 0 and one zero dword (counted in
  Size, not copied: RunPushBuffer copies Size − 4). The record's +4 is
  the strip's index count less 2, degenerate joins included.
- A `bmsh` payload is its count, a pointer to the groups at +8, the
  40-byte groups, then per group its palette (i32 bones) right after the
  last group's vertices and its vertices from the next 16-byte boundary.
  The only relocated fields are each group's `gshd` index (+32) and the
  body's LOD list; no `bmsh` is two bodies' mesh.

`body_codec.write_asset` writes an edited asset (new or removed
vertices, triangles, groups, bones): a group whose triangles are its
stored ones keeps its push buffer, any other gets a new strip (greedy
runs with swaps, 1.628 indices a triangle over the disc's 379,171 against
vanilla's 1.635); a group past 31 palette bones, 65,536 vertices or
22,392 B of push buffer (vanilla's largest, magmar's) is split into
groups of its material; the two payloads grow in place by whole pages
(§ "Appending resources") and the `bmsh`'s relocations follow its
groups. The grown file's other 3,392 payloads, their page offsets, every
other relocation and every named row are unchanged (female_2's skin with
each of its 3,051 triangles split in three: 1,899 → 4,950 vertices, two
groups for the push buffer's cap, the file 67,672,859 → 67,873,567 B;
Step 2.154's topology probe).
`body_codec.subset` cuts an asset to named groups per LOD (the other LODs
and groups dropped), the bones their palettes name and those bones'
ancestors, renumbered in order with each palette and parent following,
and named markers (Step 2.159b: the townswomen's thrown vase is
female_0_base's LOD0 vase group on its root bone `vase_joint`; her LOD1
vase rides `root_joint`, so the cut keeps LOD0 alone).

**LODs added, written over and dropped** (Step 2.166a, D537): a LOD the
asset adds (its `bmsh` unset: one
[`decimate.py`](../src/azurkit/tools/characters/decimate.py) cut from the LOD
before) is written as a new unnamed `bmsh` appended to the file
(§ "Appending resources": a page of its own, so a load run of its own, as
every vanilla LOD 1+ is; its groups' `gshd` fields its relocations),
reached only through the body's LOD list, which stays relocated; the
counts at +8 and +16 follow the list, and the new LOD's pair, records and
push buffers join the body's. A LOD given one of the body's own `bmsh`
entries is written over it. A LOD the asset leaves out is dropped: the
count falls and its `bmsh` stays in the file, in no body's list, so no
load reaches it. female_2 with LODs cut at 0.32 and 0.16 of her 5,151
triangles (1,647 and 824): two new runs of 84 and 52 KiB and her body's
run 32 → 44 KiB, nothing else of hers changed; dropped again, her own runs
are vanilla's; catalisk's LOD 1 cut anew leaves her LODs 0, 2 and 3 byte
for byte (`tests/test_model_lods.py`; Step 2.166a's LOD writer) [not yet seen in xemu: the
design's sitting X-L4].

---

## Packs and mods files that edit `.xbr` files

Modkit's `XBR_PACKS.md`, cut to what binds AzurKit's engine (AGENTS.md
§ Packs is the rule and wins where the two differ).

- **Two ways in.** A pack's slider on a config.xbr cell is an
  `XbrParametricEdit` (`src/azurkit/tools/mods/engine.py`): its value
  goes into one number cell, or multiplies the cells its pack picks from
  the vanilla tables, and nothing is written at its default. Any other
  `.xbr` edit is a mods file's `data` layer of `xbr` operations
  (`src/azurkit/edits/xbr.py`), applied in order after the packs: `set`
  a keyed cell by the file's own names, or `replace_bytes` at an offset
  of any XBR file where the vanilla file holds `expected`. Both are
  planned against the vanilla file as parsed
  (`src/azurkit/core/xbr/edits.py`): every cell is 16 bytes, so nothing
  grows. The page's Data tab ([`GUIDE.md`](GUIDE.md) § Data) writes
  `set` operations; `python -m devkit xbr inspect | xref | edit` reads
  and edits any `.xbr` on disk (`devkit/xbr/README.md`).
- **Names.** A cell is named by config.xbr's own table (§ "Table
  names"), entity (a column) and property (a row), with D51's
  spellings: case-blind, `_` read as a space, an exact name first, a
  spelling of several names refused. An entity naming several columns
  (`critters_flocking`'s two `good_noreht`) takes `col`, the column's
  index; without it, the last (§ "Duplicate entity names").
- **Empty cells.** With `fill` a `set` may write an empty (type-0)
  cell, which becomes a number or a string cell; it is refused where
  the row holds only the other kind (no vanilla row mixes them).
  Seen in xemu (Step 2.100): sweep1's empty `Damage multiplier`, which
  the game reads as 1.0, filled at 3.0 took 60 HP off a blaze sentinel
  where vanilla's level-3 hit took 20 (levels 1 and 2 unmeasured).
- **Strings.** config.xbr interns identical strings, so one pool string
  can back many cells and names (earth_armor_1/2/3's `Type` share one
  `erth`); in vanilla 8,261 of the 8,603 string cells outside the
  entity-name row share theirs. Text set into a string cell points it
  at the first string of its table that holds the text; else, when
  nothing else shares its string, rewrites it in place if it fits its
  slot; else it is refused by name (a longer string needs pool growth,
  § Backlog 6).
- **Values.** Any finite number (D23): a slider's `slider_min` and
  `slider_max` are display hints whose track holds its default and the
  vanilla value (D42). Where the game reads the cell as an int32
  (`edits/xbr.py`'s `INT32`: how it makes one, a truncation or Starting
  HP's FISTP rounding), a value an int32 can't hold is refused (D45);
  NaN and infinity are refused by name.
- **The engine must read the cell.** Show that the engine consumes a
  cell for what the edit wants before a pack writes it: `player_max_hp`
  wrote `critters_damage`'s garret4 `hitPoints` until 2026-10-09, which
  the player never uses (`RE_MOVEMENT.md` § "Player HP comes from
  settings_foo"). The two reference packs are config.xbr-only:
  `player_max_hp` (two `settings_foo` cells, Starting HP and the health
  bar's full scale) and `air_shield_flaps` (`armor_properties`' `Flaps`,
  a slider per air shield: the 15×19 table the engine loads as
  `config/armor_properties`, AZ-113).
- **A new pack** owes what AGENTS.md § Packs and § The goldens say (its
  goldens through their recorder, no byte test of its own) and is seen
  once in xemu before it is done: the goldens check bytes, not the
  gameplay effect.

## Known limitations

These aren't gaps in the reversal, they're intentional scope
boundaries of the current mod platform.  Documented so modders
know not to expect them.

- **`python -m devkit builds verify-patches` reads the XBE only.**  It
  reads each pack's XBE sites of a build; a config.xbr slider's cells
  are read back by the build's own manifest check (`azurkit open`, every
  file against the manifest), and `python -m devkit xbr verify <file>`
  checks a file's round trip and refs.

- **The randomizer writes levels its own way.**  Its writer
  (`src/azurkit/tools/randomizer/writer.py`) repoints the level
  generators in place and reads the build back; it isn't an `xbr`
  operation.

## Backlog

Ordered roughly by demand vs. cost.

1. ~~index.xbr pool base~~: done (AZ-218, 2026-10-11): there is no
   pool base, the records point at their strings relative to their own
   fields (§ "`indx` payload").  The sorted record insert and the moved
   trailer are `add_index_records` (Step 2.86, § "Appending
   resources").
2. ~~TOC entries 15/16 as keyed tables~~: done in AzurKit, whose
   `keyed.py` reads `damage` (0x83000) and `magic` (0x86000; stored
   offsets, relative to the data area, so file offsets 0x84000 and
   0x87000) as keyed tables like the other 16.
3. **Level-XBR `node` section: write support.**  Highest-value level tag
   (entity placements, exits, save points, locks).  The record table
   and the common fields are decoded (§ "Level node graph",
   2026-10-10); the links, curves, combiner and `gameState` constants,
   switches, latches, platforms and generators since Step R1.1
   (§ "Links, curves and logic nodes", `509d898ba`), and
   `src/azurkit/core/xbr/nodes.py` reads them (`be6d314c9`).  Left is write
   support in the document model (node-section writes, for R2.3 and
   R2.5).
4. **Graphics resources beyond `surf`'s header.**  `surf` is
   textures, not geometry (§ "Graphics resources"); `rdms`, `gshd`,
   `pbrc`/`pbrw` and `body`/`bmsh` rest on Level Studio's reading
   (`render.py` reads all but `body`/`bmsh`, read-only).  Only needed
   for texture or mesh edits (HM-15).
5. ~~Header bytes `0x14..0x1F`~~: done (2026-10-11): 0x14–0x38 index
   the trailer, and `0xBDC10` computes its size (§ "Header").
6. **Growing a payload** (config.xbr rows and strings).  Not built:
   nothing adds or removes a row or grows a string pool, and a text
   `set` refuses a string longer than its slot or one the pool shares
   (§ "Packs and mods files that edit `.xbr` files").  The tables don't overlap: every ref lands in its own
   payload (§ "Keyed-table sections") and the payloads tile in TOC
   order (AZ-124); the old "pool-overlap" reason came from the
   misframing AZ-124 fixed (AZ-248).  Any growth or shrink rewrites
   the entry's TOC `size` (+4, the payload length the engine reads;
   § "Table of contents"), even inside the padding.  A writer also
   has to:
   - for a new or removed row, add or drop its 8 B row header and one
     16 B cell per column, which moves the cell grid (column-major)
     and the strings after it, so it rewrites every self-relative ref
     (§ "Pointer graph") and updates `num_rows`, `total_cells` and
     `cell_data_off`;
   - for a table that outgrows the zero padding after it, move every
     later payload (keeping its alignment), rewrite their TOC offsets,
     move the trailer (still a multiple of 0x1000) and patch header
     words 0x18, 0x20, 0x28, 0x30 and 0x34 (§ "Header", § "The
     trailer").

   config.xbr has no relocations, and its named rows hold a TOC index
   and a pool offset, so neither changes; builds already rewrite the
   file's `filelist.txt` line.  Vanilla config.xbr leaves 0xD7–0xF60 B
   of zero padding before each next payload and 0x1AD4 B after the
   last table, before the trailer at 0x8A000, and starts all 18
   payloads on a 0x1000 boundary although every `flags` is 8
   [verified 2026-10-11: Step 2.17g's check script, counts and offsets
   only].  It
   needs the writer and one xemu load of a grown table [inferred: the
   engine finds the tables by name and TOC index, not at fixed
   offsets].
