"""AzurKit's icon (Step 4.1g2; D891, D892): original art that code in
``assets/icon/`` makes, no game pixel in it (D886, D890). ``mark.py`` draws the
mark and ``tile.py`` puts it on the Mac app's azure tile; ``render.py`` (the
``icon`` group, macOS) renders them into the app's ``.icns`` and the site's
favicon. The app and the site serve them (``tests/test_hosts.py``,
``tests/test_site.py``)."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from assets.icon import mark, tile
from scripts import freeze

ROOT = Path(__file__).resolve().parent.parent
# Apple's ten iconset images by their .icns type: 16, 32 and 32 px (16@2x), 64 (32@2x), 128, 256 (128@2x), 256,
# 512 (256@2x), 512 and 1024 (512@2x)
ICONSET = ("ic04", "ic05", "ic11", "ic12", "ic07", "ic13", "ic08", "ic14", "ic09", "ic10")


def test_the_sources_make_the_committed_masters_and_the_icons_hold_every_size():
    """The generators write the committed SVG masters byte for byte; the
    ``.icns`` holds Apple's ten iconset images (and its ``info``), the
    favicon 16, 32 and 48 px frames, and ``favicon-32.png`` is 32 px."""
    made = {"AzurKit.svg": mark.svg()}
    made |= tile.svgs(made["AzurKit.svg"])
    assert {name: hashlib.sha256(svg.encode()).hexdigest() for name, svg in made.items()} == {
        name: hashlib.sha256((ROOT / "assets" / "icon" / name).read_bytes()).hexdigest()
        for name in ("AzurKit.svg", "AzurKit-tile.svg", "AzurKit-tile-small.svg")}

    icns, types, at = freeze.ICON.read_bytes(), [], 8
    assert (icns[:4], struct.unpack(">I", icns[4:8])[0]) == (b"icns", len(icns))
    while at < len(icns):
        types.append(icns[at:at + 4].decode())
        at += struct.unpack(">I", icns[at + 4:at + 8])[0]
    assert (at, sorted(types)) == (len(icns), sorted([*ICONSET, "info"]))

    ico = (ROOT / "web" / "favicon.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind, [ico[6 + 16 * i] for i in range(count)]) == (0, 1, [16, 32, 48])
    assert struct.unpack(">4sII", (ROOT / "web" / "favicon-32.png").read_bytes()[12:24]) == (b"IHDR", 32, 32)
