# devkit/builds: the build checks (dev only)

Modkit's `azurik-mod verify-patches` and `inspect-physics`. Each reads any
build's `default.xbe` (`--iso IMAGE`, its `gamedata/config.xbr` too, or
`--xbe XBE`): an AzurKit build, a Modkit one or another, of either release,
told by the kernel thunk table's address its header keeps. Each site is
read at that release's own address (the facts, `src/azurkit/core/facts.<release>.json`)
and compared with the release's vanilla `default.xbe`: `--original IMAGE|XBE`,
else the player's image (`AZURKIT_ISO` or `AZURKIT_ISO_EUROPE`, else the
user data folder). Nothing prints a byte: a site that holds neither is its
length and sha256[:12]. A build it can't read (or cut short), of neither release, or no
vanilla XBE to compare with is one `VERB: ...` line on stderr and exit 2.

```bash
uv run --locked python -m devkit builds VERB (--iso IMAGE | --xbe XBE) [--original IMAGE|XBE] ...
```

| Verb | What it prints |
|---|---|
| `verify-patches [--strict]` | each pack's fixed patches (applied, original or mismatch, with the first offset where a mismatch parts from each), sliders at a site (default with the value vanilla holds, custom with the build's, or virtual), trampolines (applied: a CALL or JMP into the shim room, the rest NOPs), how many of a `custom_apply` pack's footprint places the build wrote, the frame-rate guard (the rate the main loop holds and every place fps_unlock writes at it, the step cap among them: Modkit's safety-critical guard), how many of the player-model swap's sites it wrote, and each run of bytes that differs outside all of those and the shim room (`.text`'s growth, `SHIMS`), the header held to the state they derive (`core.xbe.grown`); exit 1 on a mismatch or a failed guard, and with `--strict` on such a run |
| `inspect-physics [--json]` | each player_physics slider site: `VANILLA`, `PATCHED` with the value it holds (and where the code reads it: a float carved in the shim room, a hand shim's k) or `DRIFTED`; gravity, the two fuel costs and the seven air-control speeds against vanilla's, the four loads (swim, jump and flap's gravity x k^2, the far-descent flap), the four hand shims (roll distance and speed, climb, the flap ceiling), the speed toggle's hook and walk's runSpeed in config.xbr (`NOT READ` for `--xbe`) |

```bash
uv run --locked python -m devkit builds inspect-physics --iso build.iso          # did the sliders land?
uv run --locked python -m devkit builds verify-patches --iso build.iso --strict
```

Where they differ from Modkit's: they read AzurKit's packs (17, by Modkit's
names), so fps_unlock, qol_alloc_race and enemy_scaling, which write their
own sites here, are counted by place; Modkit's safety-critical flag is the
frame-rate guard; a swap site is allowed whole, where Modkit allowed each
hook only where it calls into the room; the vanilla XBE is always the
comparison (Modkit's whitelist ran only with `--original`); and
`inspect-physics` also reads roll speed, climb and the speed toggle.
`tests/test_devkit_builds.py` pins them.

## write-manifest

Modkit's `azurik-mod iso-verify --write-manifest`: a release's manifest,
`src/azurkit/core/manifests/<release>.json` (each folder of its image and
each file's size and sha256, by path: what `azurkit verify` and every build
check an image against), written from that release's exact vanilla image,
which the gate's releases name by the whole image's size and sha256
(`gate.Release.iso_size`, `iso_sha256`); any other image is refused by name
and nothing is written. The layout is Modkit's byte for byte; the file is
written whole (a part file renamed into place), and only counts and paths
are printed. A changed manifest is a protected path: its commit names it.

```bash
uv run --locked python -m devkit builds write-manifest                 # each release's image the resolver finds
uv run --locked python -m devkit builds write-manifest --iso usa.iso --out /tmp/x/usa.json   # elsewhere
```

`--out` never names the image or a release's vanilla image the resolver
finds (D36). A refusal is one `write-manifest:` line on stderr and exit 1. The two images
never change (D146), so a rewrite gives the files AzurKit ships;
`tests/test_gate.py` pins the writer on a synthetic image.
