# devkit/xbr: the XBR file tools (dev only)

Modkit's `azurik-mod xbr` verbs, on AzurKit's parse (`src/azurkit/core/xbr/`).
Each reads `.xbr` files on disk: `azurkit files IMAGE --extract gamedata/a1.xbr
--out a1.xbr` writes one out of an image. A file it can't read, or one that
isn't an XBR, is one `xbr VERB: ...` line on stderr and exit 1.

```bash
uv run --locked python -m devkit xbr VERB [ARGS ...]
```

| Verb | What it does |
|---|---|
| `inspect FILE --tag TAG [--entries N] [--stride N] [--fields-per-row N] [--hex] [--json]` | the first N records (3) of the first entry tagged TAG, each 4-byte column labelled by the first reading that fits: `zero`, `fourcc`, `int32` (a small whole float), `f32`, `ptr` (an XBE address), `off` (inside the file), `int32`, `u32`; the stride is detected unless given; `--hex` adds each column's bytes (a human's: it prints the file's bytes) |
| `diff A B [--min-len N] [--max-strings N] [--json]` | each tag whose total size changed, the strings (N or more ASCII characters with a letter, 6) each tag gained or lost, and each same-index, same-tag, same-size entry whose bytes differ (its first differing offset and how many); exit 1 when the files differ, 0 when they don't |
| `edit IN OUT [--set-string OLD=NEW [--tag TAG]] [--replace-bytes OFFSET:HEX] [--set-value TABLE/ENTITY/PROP=NUMBER] [--set-keyed-string TABLE/ENTITY/PROP=TEXT]` | the edits in that order, each repeatable, written to OUT whole or not at all: a string in place (it must fit the old one's slot), bytes at an offset, a keyed table's number cell (any finite value) or string cell (`core.xbr.edits.set_text`: it points at a string of its table, else rewrites its own where it fits); OUT is never IN or a vanilla image |
| `xref FILE [--tag TAG] [--section-index N] [--format text\|json] [--list-all]` | the pointer fields the parse models, by owner tag: each keyed table's row names and string cells (config.xbr's 18 tables: 10,340), and the sections no parse models (every tag but `tabl` and `indx`) |
| `verify FILE [--cross-check-schema]` | that the file parses whole (`core.xbr.Document`: the header, TOC, trailer, names and every keyed table, so no modelled pointer leaves its table); `--cross-check-schema` lists each pack's config.xbr slider whose cell `src/azurkit/tools/data/schema.json` doesn't document (a warning) |

```bash
uv run --locked python -m devkit xbr inspect w1.xbr --tag surf                 # 16-byte records, detected
uv run --locked python -m devkit xbr edit config.xbr out.xbr --set-value damage/norm_1/Damage=5
uv run --locked python -m devkit xbr verify out.xbr --cross-check-schema
```

Where they differ from Modkit's: `xref` and `verify` count config.xbr's
damage and magic tables' pointers too (Modkit read those two as fixed-stride
records with none, its Q160), and `edit` writes their cells; `inspect`
shows a column's bytes only with `--hex`; `edit`'s `--add-row`,
`--remove-row` and `--grow-pool`, which Modkit only refused, aren't here.
`tests/test_devkit_xbr.py` pins them.
