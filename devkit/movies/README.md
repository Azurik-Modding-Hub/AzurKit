# devkit/movies: the movie tools (dev only)

Modkit's `azurik-mod movies` verbs. The game's 14 movies (`movies/*.bik` in
an image; `azurkit files IMAGE --extract movies/Title.bik --out Title.bik`
writes one out) are Bink 1 (`BIKi`) files, 640x480 at 30 fps with one audio
track. A refusal is one `movies VERB: ...` line on stderr and exit 1.

```bash
uv run --locked python -m devkit movies VERB [ARGS ...]
```

| Verb | What it does |
|---|---|
| `info PATH [--json]` | a `.bik`'s header: its size, resolution, frame count, frame rate, length, audio tracks, largest frame and flags; a folder's `.bik` files (directly in it) as a table, with their total size and length |
| `frames BIK --out DIR [--pattern P] [--dry-run] [--json]` | its frames as PNGs into DIR (never the input), by ffmpeg's `bink` decoder (Bink 1 is proprietary); with no ffmpeg on PATH it names it and writes nothing, a failed run names ffmpeg's last lines and removes the folder it made; `--dry-run` prints the ffmpeg command |
| `frames BIK --info [--json]` | the header and the per-frame offset table's keyframe count, no decoder: the table follows the header and a descriptor per audio track (16 bytes in the game's Bink 1.9, 12 or 8 in earlier ones, told by where the table's first offset points) |

`tests/test_devkit_media.py` pins them.
