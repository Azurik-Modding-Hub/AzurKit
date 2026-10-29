"""Rebuild AzurKit's icon from its generators (dev only, macOS: Apple's
``iconutil`` writes the ``.icns``):

    uv run --locked --group icon python assets/icon/render.py

It writes the SVG masters here (``mark.py``: ``AzurKit.svg``; ``tile.py``:
``AzurKit-tile.svg`` and ``AzurKit-tile-small.svg``), then renders what the
app and the site use: ``AzurKit.icns`` here, the Mac app's icon (the tile;
``scripts/freeze.py``), and the site's favicon, the free mark, in ``web/``
(``favicon.ico`` with 16, 32 and 48 px frames, and ``favicon-32.png``).
resvg draws the SVGs' turbulence filters; every size is rendered from its SVG
at that size, never scaled from another render: the tile's 16 and 32 px from
``AzurKit-tile-small.svg``, the rest from ``AzurKit-tile.svg``.
"""

import io
import subprocess
import sys
import tempfile
from pathlib import Path

import resvg_py
from PIL import Image

import mark
import tile

HERE = Path(__file__).resolve().parent
WEB = HERE.parent.parent / "web"


def render(svg: str, size: int) -> tuple[bytes, Image.Image]:
    """``svg`` at ``size`` px square: its PNG, and that PNG's RGBA pixels."""
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size))
    return png, Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> int:
    masters = {"AzurKit.svg": mark.svg()}
    masters |= tile.svgs(masters["AzurKit.svg"])
    for name, svg in masters.items():
        (HERE / name).write_text(svg, encoding="utf-8")

    # The favicon: the mark, free (D892). The 48 is the base so Pillow keeps every size; the 16 and 32 frames are
    # their own renders (append_images), not resamples of the 48.
    free = {size: render(masters["AzurKit.svg"], size) for size in (16, 32, 48)}
    (WEB / "favicon-32.png").write_bytes(free[32][0])
    free[48][1].save(WEB / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)],
                     append_images=[free[16][1], free[32][1]])
    with Image.open(WEB / "favicon.ico") as ico:
        for size in (16, 32, 48):
            frame = ico.ico.getimage((size, size)).convert("RGBA")
            assert frame.tobytes() == free[size][1].tobytes(), f"favicon.ico's {size} px frame isn't its render"

    # The Mac app's icon: the tile, at Apple's ten iconset sizes.
    with tempfile.TemporaryDirectory(prefix="azurkit-icon.") as tmp:
        iconset = Path(tmp) / "AzurKit.iconset"
        iconset.mkdir()
        for points in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ""), (2, "@2x")):
                size = points * scale
                svg = masters["AzurKit-tile-small.svg" if size <= 32 else "AzurKit-tile.svg"]
                (iconset / f"icon_{points}x{points}{suffix}.png").write_bytes(render(svg, size)[0])
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "AzurKit.icns")], check=True)
    for path in (*(HERE / name for name in masters), HERE / "AzurKit.icns", WEB / "favicon.ico",
                 WEB / "favicon-32.png"):
        print(f"wrote {path.relative_to(HERE.parent.parent)}: {path.stat().st_size:,} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
