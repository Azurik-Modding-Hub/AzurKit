# devkit/audio: the audio tools (dev only)

Modkit's `azurik-mod audio` verb. It reads an `.xbr` file on disk
(`azurkit files IMAGE --extract gamedata/fx.xbr --out fx.xbr` writes one
out of an image). A file it can't read or that isn't an XBR is one
`audio dump: ...` line on stderr and exit 1.

```bash
uv run --locked python -m devkit audio dump XBR --output DIR [--only-audio] [--entropy-min X] [--no-wav] \
    [--raw-previews [--preview-sample-rate R]] [--preview N] [--json]
```

Every `wave` entry of XBR (fx.xbr's sounds; a voice bank such as
`english.xbr`) goes to `DIR/waves/wave_NNNN.bin`, a streamed one (its 20
bytes name the `sdsr` entry holding its samples) with its samples filled
in. Each entry whose 16-byte header the game's parser (0xAC400) takes gets a
RIFF/WAVE beside it, `wave_NNNN.wav`, of its codec's bytes: Xbox ADPCM
(`WAVE_FORMAT_XBOX_ADPCM`, 0x0069, 36 bytes a channel a block of 64
samples), which vgmstream, Audacity and ffmpeg play, or PCM. The others are
`too-small` (under 64 bytes), `likely-animation` (a TOC tag in its first 64
bytes) or `non-audio`, which the game refuses too; `--raw-previews` wraps
those as 16-bit mono PCM to look at, not to hear. An entry the size of an
earlier one whose first 32 bytes match is marked its duplicate.

`DIR/manifest.json` lists each entry: its offset, size, class, the entropy
of its first 256 bytes, the sha256[:12] of its first 32 (never the bytes),
its header, its name from the archive's own table (`fx/sound/<entity>/<key>`)
and its files; `--json` prints it. `--only-audio` and `--entropy-min` list an
entry but don't write it. The USA image's fx.xbr has 700 waves, all Xbox
ADPCM (31 streamed, 574 named), english.xbr 234 (134 streamed), every one
with its WAV, as Modkit's dump writes them, file for file.

`tests/test_devkit_media.py` pins it.
