# devkit/re: the reverse-engineering tools (dev only)

The `re` area holds the offline XBE reads and the RE data now; the Ghidra
side (its client, serves, sync and snapshot verb) and shim authoring come with
their own steps.

## `xbe`: offline reads of a `default.xbe`

```bash
uv run --locked python -m devkit re xbe VERB [ARGS ...] [--iso PATH | --xbe PATH] [--region usa|europe] [--json]
```

A verb reads the XBE of `--iso` or `--xbe` (either takes an Xbox image or a
raw XBE), else the image of `--region`'s release: `AZURKIT_ISO` or
`AZURKIT_ISO_EUROPE`, else `usa.iso` or `europe.iso` in the user data folder
(USA's by default when found, else the only one found), whose `default.xbe`
must be that release's vanilla one. Stderr names what it read, the release
(`the USA release`, `a build of the USA release` by its kernel thunk table's
address, or `neither release`) and the XBE's `sha256[:12]`; stdout is the
verb's, JSON with `--json`. The four source flags go before the verb or
after it. A refusal (no image, not an XBE, an address no section maps, a
`--region` the XBE isn't) is one `xbe: ...` line on stderr and exit 2.

Addresses in and out are the XBE's own (hex `0x...` or decimal), mapped
through its own section table, so an appended `SHIMS` section and a section's
zero-filled tail map right. A listing line ends `  ; name` where its operands
hold an address with a name, the first of: the release's facts' function
(`src/azurkit/core/facts.<release>.json`) or kernel import's thunk slot, the
Ghidra project's function (`data/ghidra_snapshot.json`), an anchor
(`data/anchors.toml`: its name without `AZURIK_` and `_VA`, lower case), the
project's data label, and a pack's site (`pack:label`; a `custom_apply`'s
places by the pack alone, their labels following its sliders). All but the
facts' are USA addresses: Europe's XBE gets those its facts' address map
holds, at its own addresses.

| Verb | What it prints |
|---|---|
| `addr VALUE [--from va\|file]` | the number as a VA, a file offset and a section (a VA from the base address 0x10000 up, unless `--from` says) |
| `sections` | the section table |
| `read VA[:N] [--as f32\|f64\|i32\|u32\|u16\|u8\|ptr\|cstr]` | N values from VA as the game sees them, never their bytes: `bss` where the loader zero-fills; a `ptr`'s target section and its name or data C string; `cstr` N strings in a row (only in `.rdata` and `.data`) |
| `vtable VA [--slots N]` | a vtable's slots, each offset, target and name: N, else up to the first that holds no code address or is the next vtable (an instruction holds its VA) |
| `dis VA[:N] [--count N]` | N instructions from VA (default 20), `0xVA  mnemonic operands`; a byte capstone can't decode is `(bad)` |
| `fn VA` | what the function at VA reaches without a call, in address order (a heuristic: a tail `jmp` is followed, a switch's table isn't; Ghidra's body is the authority) |
| `calls [VA] [--to VA] [--section S] [--range LO:HI] [--in-fn VA]` | the direct calls (to VA) and their callees |
| `insns [--mnemonic M] [--operand TEXT] [--section S] [--range LO:HI] [--in-fn VA]` | the instructions by exact mnemonic and operand substring, case-blind |
| `sse2 [--section S]` | what the Xbox's Pentium III can't run: SSE2 and later, 3DNow!, `fisttp` and the other ungrouped ones (`pause` runs as a NOP) |
| `find-refs --va VA \| --string TEXT [--data]` | the `.text` instructions that hold VA as an immediate or a memory displacement (a relative call is `calls`'); `--string` takes the string equal to TEXT, else the one that holds it, and refuses several, listing them; `--data`: the 4-aligned data dwords that hold it (vtable and pointer-table slots) |
| `find-floats MIN MAX [--width float\|double\|both]` | the float32s and doubles in `.rdata` in [MIN, MAX], at every byte offset, never zero |
| `strings PATTERN [--regex] [-i] [--min-len N] [--limit N]` | the printable ASCII runs in `.rdata` and `.data` that hold PATTERN |
| `hexdump ADDRESS [--length N] [--file]` | the bytes from a VA (or a file offset): **a human's**, it prints the game's bytes; an agent uses `read` and `dis` |

Code is every section but `.rdata`, `.data`, `BINKDATA`, `DOLBY` and
`$$XTIMAGE`, told by name (`.rdata` is flagged executable), decoded by a
linear sweep that steps over a byte capstone can't decode, so data inside
code (a jump table) can show as instructions. USA's vanilla XBE gives 35
`sse2` hits (23 3DNow! instructions in `DSOUND`, 12 `fisttp` in `.text` and
`D3DX`) and Europe's 31: judge a patch by its own section (`--section SHIMS`).

```bash
uv run --locked python -m devkit re xbe read 0x1980A8 --as f32             # 9.8, the gravity
uv run --locked python -m devkit re xbe find-refs --string fx_magic_timer  # its 3 pushes
uv run --locked python -m devkit re xbe --region europe dis 0x41F67:1      # call 0xcb420  ; anim_marker_position
```

`tests/test_re_xbe.py` pins these. AZ-108's guard, that each facts
function pops what its declared ABI makes its caller push, is
`tests/test_shims.py`'s.

## The data: `devkit/re/data/`

The RE knowledge AzurKit's player side has no use for, from Modkit's last
cut; none of it reaches the wheel (`tests/test_wheel.py`: the wheel is
`src/azurkit`'s files).

| File | What it holds |
|---|---|
| `ghidra_snapshot.json` | the Ghidra project's names: 545 functions, 1,103 labels and 10 structures (Modkit's `docs/ghidra_snapshot.json`, as it was; only the Ghidra side's `ghidra-snapshot` writes it once that is ported) |
| `anchors.toml` | the 83 VA anchors of Modkit's shim header: each USA address, its section, what the vanilla XBE holds there (an `f32`, a `u32`, a `cstr`, a `wstr` or `zero` bytes) or, in `.text`, nothing (code), and a note |
| `structs.h` | the header's 10 structures and 2 enums with their offset asserts, the player entity's field offsets and flag bits and the vanilla step; no shim includes it (they include shimkit's headers) |
| `function_notes.toml` | a note for each of the facts' 354 functions: what it does and what a shim calling it must know (Modkit's vanilla-symbol registry's docs) |

`tests/test_re_xbe.py` holds both releases' XBEs to the anchors (Europe's
addresses from the facts' address map), each anchor to one check, the
anchors to `anchors.toml` alone, `structs.h` to compiling with shimkit's
flags (its asserts holding) and the notes to the facts' functions.
